#!/usr/bin/env bash
set -o errexit

echo ">>> Установка зависимостей"
pip install -r requirements/requirements.txt

echo ">>> Сборка статики"
python manage.py collectstatic --no-input

echo ">>> Применение миграций"
python manage.py migrate

echo ">>> Заполнение БД тестовыми данными"
python manage.py seed

# Создаём суперюзера, если заданы env-переменные и юзера ещё нет
if [ -n "$DJANGO_SUPERUSER_EMAIL" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo ">>> Создание суперюзера"
  python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
import os
email = os.environ['DJANGO_SUPERUSER_EMAIL']
if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(
        email=email,
        password=os.environ['DJANGO_SUPERUSER_PASSWORD'],
        first_name=os.environ.get('DJANGO_SUPERUSER_FIRST_NAME', 'Admin'),
    )
    print('Суперюзер создан:', email)
else:
    print('Суперюзер уже существует:', email)
"
fi

echo ">>> Сборка завершена успешно"