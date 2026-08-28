from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

from .managers import UserManager

phone_validator = RegexValidator(
    regex=r"^\+?[0-9\s\-()]{7,20}$",
    message="Телефон может содержать только цифры, пробелы, скобки, дефис и ведущий «+».",
)


class User(AbstractUser):
    """Кастомный пользователь с email-логином вместо username."""

    username = None
    email = models.EmailField(unique=True, verbose_name="Email")
    first_name = models.CharField(max_length=150, blank=True, verbose_name="Имя")
    last_name = models.CharField(max_length=150, blank=True, verbose_name="Фамилия")
    phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Телефон",
        validators=[phone_validator],
        help_text="Например, +998901234567",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["-date_joined"]

    def save(self, *args, **kwargs):
        # Единое нормализованное написание: иначе регистрация «Ivan@Gmail.com» и вход
        # «ivan@gmail.com» живут в разных вселенных, а уникальность-то точная.
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
