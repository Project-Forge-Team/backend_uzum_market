from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

from .managers import UserManager

# Формат «+998XX XXX XX XX» либо пустая строка (§5.1 ТЗ).
phone_validator = RegexValidator(
    regex=r"^\+?[\d\s()\-]{9,18}$",
    message="Телефон в формате +998901234567 (или оставьте поле пустым).",
)


class User(AbstractUser):
    """Кастомный пользователь с email-логином вместо username.

    Пароль — стандартный хэш Django (argon2id, см. PASSWORD_HASHERS): не md5 и не plaintext.
    """

    username = None
    email = models.EmailField(unique=True, verbose_name="Email")
    first_name = models.CharField(max_length=60, blank=False, verbose_name="Имя")
    last_name = models.CharField(max_length=60, blank=True, verbose_name="Фамилия")
    phone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="Телефон",
        validators=[phone_validator],
        help_text="Например, +998901234567",
    )
    # should из ТЗ: для инвалидации сессий после смены пароля.
    password_updated_at = models.DateTimeField(null=True, blank=True, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["-date_joined"]

    def save(self, *args, **kwargs):
        # Единое нормализованное написание: регистрация «Ivan@Gmail.com» и вход
        # «ivan@gmail.com» — один и тот же аккаунт.
        if self.email:
            self.email = self.email.strip().lower()
        if self.phone:
            self.phone = self.phone.strip()
        super().save(*args, **kwargs)

    def set_password(self, raw_password):
        from django.utils import timezone

        super().set_password(raw_password)
        self.password_updated_at = timezone.now()

    def __str__(self):
        return self.email
