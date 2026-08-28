from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Менеджер для email-логина.

    Штатный `django.contrib.auth.models.UserManager` ждёт `username` первым
    позиционным аргументом и падает на `create_user(email=…)` — из-за этого
    `manage.py createsuperuser` в этом проекте был нерабочим (в build.sh суперюзера
    создавали обходным путём через `shell -c`).

    `get_by_natural_key` — логин по email без учёта регистра: регистрация приводит email
    к lower(), поэтому 'Probe@Example.COM' в форме логина раньше давал 401.
    """

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Электронная почта обязательна для создания пользователя.")
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        user = self.create_user(email, password, **extra_fields)
        user.is_active = True
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, username):
        field = self.model.USERNAME_FIELD
        try:
            # быстрый путь: точное совпадение (индекс по unique-полю)
            return self.get(**{field: username})
        except self.model.DoesNotExist:
            pass
        candidates = list(self.filter(**{f"{field}__iexact": str(username).strip()}).order_by("id")[:2])
        if not candidates:
            raise self.model.DoesNotExist(f"Пользователь с {field}={username!r} не найден.")
        if len(candidates) > 1:
            # данные уже повреждены (регистрация в разные годы): молча выбрать один — хуже
            raise self.model.MultipleObjectsReturned(
                f"На {field}={username!r} найдено несколько пользователей разной регистровой формы."
            )
        return candidates[0]
