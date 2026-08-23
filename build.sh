#!/usr/bin/env bash
set -o errexit

# Устанавливаем зависимости
pip install -r requirements/requirements.txt

# Собираем статику
python manage.py collectstatic --no-input

# Применяем миграции
python manage.py migrate