#!/usr/bin/env bash
set -o errexit
set -o pipefail

# --- 1. Проверка версии Python ---------------------------------------------------
# Django 6.1 требует Python >= 3.12. Без этой проверки на Render (где у ранее созданного
# сервиса может остаться дефолт 3.11) сборка падала невнятным
# «No matching distribution found for Django==6.1».
python3 - <<'PY'
import sys

need, got = (3, 12), sys.version_info[:2]
if got < need:
    sys.exit(
        "Python {}.{} слишком стар: Django 6.1 требует >= 3.12.\n"
        "Задайте PYTHON_VERSION=3.12 в настройках сервиса (или файл .python-version).".format(*got)
    )
print(f">>> Python {sys.version.split()[0]} — ок")
PY

# --- 2. Зависимости ---------------------------------------------------------------
echo ">>> Установка зависимостей"
pip install -r requirements/requirements.txt
# Хранилище загрузок в S3 включён (USE_S3=True) — доставляем django-storages.
if [ "${USE_S3:-False}" = "True" ]; then
  pip install -r requirements/storage.txt
fi

# --- 3. Конфигурация --------------------------------------------------------------
echo ">>> Проверка конфигурации"
python manage.py check

echo ">>> Сборка статики"
# STATIC_MANIFEST_REQUIRED=1 — чтобы WhiteNoise гарантированно использовал Manifest-хранилище
# и сгенерировал хэши + staticfiles.json (на первом билете манифеста на диске ещё нет).
# Переменная задаётся только для этой команды: рантайм-процесс должен выбирать хранилище по факту
# собранной статики, а не по «наследству» из build.sh.
STATIC_MANIFEST_REQUIRED=1 python manage.py collectstatic --no-input

echo ">>> Применение миграций"
python manage.py migrate --noinput

# --- 4. Демо-данные ---------------------------------------------------------------
# seed по умолчанию ничего не переписывает: он делает один exists()-запрос и выходит.
# «Починка кодировки» (полный скан таблицы) больше не запускается на каждом деплое —
# она только по флагу:  python manage.py seed --fix-encoding
if [ "${SEED_DEMO_DATA:-False}" = "True" ]; then
  echo ">>> Заполнение БД тестовыми данными"
  python manage.py seed
else
  echo ">>> SEED_DEMO_DATA != True — демо-данные не заливаем"
fi

# --- 5. Суперюзер -----------------------------------------------------------------
# Идемпотентная команда ensure_superuser. Заменяет createsuperuser --noinput, который
# в этом проекте ронял сборку:
#   - `manage.py shell -c` пишет в stdout служебную строку (banner) + пустую строку + `True`,
#     поэтому `[ "$EXISTS" = "True" ]` никогда не истинно и деплой уходил в else;
#   - `createsuperuser --noinput` бросал `CommandError("That Email is already taken.")`,
#     а `set -o errexit` валил весь билд.
# Команда ищет пользователя как логин (iexact + strip), при повторном деплое просто
# повышает флаги и НЕ трогает пароль существующего пользователя (иначе каждый деплой
# отменял бы смену пароля в админке). Пароль обновляется только с --update-password
# (или DJANGO_SUPERUSER_UPDATE_PASSWORD=True).
echo ">>> Суперюзер"
SUPERUSER_ARGS=()
if [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ]; then SUPERUSER_ARGS+=(--email "$DJANGO_SUPERUSER_EMAIL"); fi
if [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then SUPERUSER_ARGS+=(--password "$DJANGO_SUPERUSER_PASSWORD"); fi
if [ -n "${DJANGO_SUPERUSER_FIRST_NAME:-}" ]; then SUPERUSER_ARGS+=(--first-name "$DJANGO_SUPERUSER_FIRST_NAME"); fi
if [ -n "${DJANGO_SUPERUSER_LAST_NAME:-}" ]; then SUPERUSER_ARGS+=(--last-name "$DJANGO_SUPERUSER_LAST_NAME"); fi
if [ "${DJANGO_SUPERUSER_UPDATE_PASSWORD:-}" = "True" ]; then SUPERUSER_ARGS+=(--update-password); fi
python manage.py ensure_superuser "${SUPERUSER_ARGS[@]}"

echo ">>> Сборка завершена успешно"
