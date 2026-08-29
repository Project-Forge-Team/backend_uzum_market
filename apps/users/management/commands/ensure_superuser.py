"""Идемпотентное создание/повышение суперюзера для build.sh.

Заменяет `createsuperuser --noinput`, который в этом проекте нерабочий:
1. `manage.py shell -c` пишет в stdout служебную строку
   (`... objects imported automatically ...`) + пустую строку + `True`, поэтому
   `[ "$EXISTS" = "True" ]` в bash никогда не истинно — деплой уходил в `else`;
2. `createsuperuser --noinput` бросает `CommandError("That Email is already taken.")`,
   а `set -o errexit` в build.sh роняет весь билд.

Семантика команды:
  * опции (--email/--password/--first-name/--last-name/--update-password) падают на
    env `DJANGO_SUPERUSER_EMAIL/_PASSWORD/_FIRST_NAME/_LAST_NAME/_UPDATE_PASSWORD`;
  * пустой email → warning и выход с кодом 0 (в деплое это штатно);
  * поиск — `get_by_natural_key(email)` (iexact + strip, как логин), НЕ точное сравнение;
  * не найден → `create_superuser(...)`; без пароля → `CommandError`;
  * найден → ничего не создаём: поднимаем `is_staff`/`is_superuser`, нормализуем email,
    (опционально) имя/фамилию, пароль НЕ трогаем без `--update-password`.
"""

import os
from argparse import ArgumentParser

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# Имена env-переменных собраны в dict: иначе ruff ругается S105 («Possible hardcoded
# password») на строке `ENV_PASSWORD = "DJANGO_SUPERUSER_PASSWORD"`.
ENV_NAMES = {
    "email": "DJANGO_SUPERUSER_EMAIL",
    "password": "DJANGO_SUPERUSER_PASSWORD",
    "first_name": "DJANGO_SUPERUSER_FIRST_NAME",
    "last_name": "DJANGO_SUPERUSER_LAST_NAME",
    "update_password": "DJANGO_SUPERUSER_UPDATE_PASSWORD",
}

User = get_user_model()


class Command(BaseCommand):
    help = "Идемпотентно создаёт/повышает суперюзера (безопасно для повторного деплоя)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--email", help="Email суперюзера (fallback: DJANGO_SUPERUSER_EMAIL)")
        parser.add_argument("--password", help="Пароль (fallback: DJANGO_SUPERUSER_PASSWORD)")
        parser.add_argument("--first-name", dest="first_name", help="Имя (fallback: DJANGO_SUPERUSER_FIRST_NAME)")
        parser.add_argument("--last-name", dest="last_name", help="Фамилия (fallback: DJANGO_SUPERUSER_LAST_NAME)")
        parser.add_argument(
            "--update-password",
            action="store_true",
            help="Обновить пароль существующего суперюзера (fallback: DJANGO_SUPERUSER_UPDATE_PASSWORD). "
            "Без этого флага пароль существующего пользователя НЕ трогается.",
        )

    @staticmethod
    def _from_env(name: str) -> str:
        return os.getenv(ENV_NAMES[name], "").strip()

    @staticmethod
    def _flag(value: str) -> bool:
        return value.lower() in ("1", "true", "yes", "on")

    def handle(self, *args, **options):
        email = (options.get("email") or self._from_env("email")).strip()
        password = options.get("password") or self._from_env("password")
        first_name = (options.get("first_name") or self._from_env("first_name")).strip()
        last_name = (options.get("last_name") or self._from_env("last_name")).strip()
        update_password = options.get("update_password") or self._flag(self._from_env("update_password"))

        if not email:
            self.stdout.write(self.style.WARNING(f"{ENV_NAMES['email']} не задан — суперюзер не создаётся."))
            return

        with transaction.atomic():
            try:
                user = User._default_manager.get_by_natural_key(email)
            except User.DoesNotExist:
                self._create(email, password, first_name, last_name)
            except User.MultipleObjectsReturned:
                raise CommandError(
                    f"На {email!r} найдено несколько пользователей разной регистровой формы. "
                    "Разберитесь в БД вручную (приведите email к единому регистру)."
                ) from None
            else:
                self._update(
                    user,
                    email,
                    first_name,
                    last_name,
                    update_password,
                    password,
                )

    def _create(self, email: str, password: str, first_name: str, last_name: str) -> None:
        if not password:
            raise CommandError(
                f"Для создания суперюзера {email!r} нужен пароль: задайте --password или {ENV_NAMES['password']}."
            )
        User.objects.create_superuser(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        self.stdout.write(self.style.SUCCESS(f"Суперюзер создан: {email}"))

    def _update(
        self, user, requested_email: str, first_name: str, last_name: str, update_password: bool, password: str
    ):
        """Повышаем существующего пользователя до суперюзера — ничего не дублируем."""
        changed = []
        normalized = requested_email.strip().lower()

        if normalized != user.email:
            # Нормализуем email, но только если нет ДРУГОЙ строки с таким email.
            if User.objects.filter(email=normalized).exclude(pk=user.pk).exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"Email {user.email!r} ≠ {normalized!r}, но строка с нормализованным email уже"
                        " существует — не трогаю. Выполните слияние вручную."
                    )
                )
            else:
                user.email = normalized
                changed.append("email")

        if not user.is_staff:
            user.is_staff = True
            changed.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            changed.append("is_superuser")
        if first_name and first_name != user.first_name:
            user.first_name = first_name
            changed.append("first_name")
        if last_name and last_name != user.last_name:
            user.last_name = last_name
            changed.append("last_name")
        if update_password:
            if not password:
                raise CommandError(
                    f"--update-password задан, но пароль пуст: задайте --password или {ENV_NAMES['password']}."
                )
            user.set_password(password)
            changed.append("password")

        if changed:
            user.save(update_fields=changed)
            self.stdout.write(self.style.SUCCESS(f"Суперюзер обновлён: {user.email} ({', '.join(changed)})"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Суперюзер уже в порядке: {user.email}"))
