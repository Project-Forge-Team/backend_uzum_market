"""Сериализаторы авторизации (§5.1 ТЗ)."""

import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import exceptions, serializers

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
PASSWORD_MIN = 8

User = get_user_model()


def validate_email_value(value: str) -> str:
    value = (value or "").strip()
    if not EMAIL_RE.match(value):
        raise serializers.ValidationError("Введите корректный email.")
    return value.lower()


def validate_phone_value(value: str) -> str:
    """Телефон необязателен, но если заполнен — по формату из ТЗ."""
    value = (value or "").strip()
    if value:
        try:
            User._meta.get_field("phone").run_validators(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages[0]) from exc
    return value


class UserSerializer(serializers.ModelSerializer):
    """UserProfile из ТЗ: публичная часть без хэшей."""

    is_seller = serializers.SerializerMethodField()
    seller_id = serializers.SerializerMethodField()
    date_joined = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "date_joined", "is_seller", "seller_id"]
        read_only_fields = fields

    def get_is_seller(self, obj) -> bool:
        return self._shop(obj) is not None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_seller_id(self, obj):
        shop = self._shop(obj)
        return shop.pk if shop else None

    @staticmethod
    def _shop(obj):
        # Reverse OneToOne: у пользователя без магазина obj.shop кидает
        # RelatedObjectDoesNotExist (наследник AttributeError) → getattr-дефолт работает.
        return getattr(obj, "shop", None)

    def get_date_joined(self, obj) -> str:
        from apps.core.datetime import iso_utc

        return iso_utc(obj.date_joined)


class RegisterSerializer(serializers.Serializer):
    """POST /auth/register/: email, password, password2, first_name, last_name, phone, shop_name?"""

    email = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=60)
    last_name = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    shop_name = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        value = validate_email_value(value)
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Пользователь с таким email уже зарегистрирован.")
        return value

    def validate_password(self, value):
        if len(value or "") < PASSWORD_MIN:
            raise serializers.ValidationError(f"Пароль должен быть не короче {PASSWORD_MIN} символов.")
        return value

    def validate_first_name(self, value):
        value = (value or "").strip()
        if len(value) < 2:
            raise serializers.ValidationError("Имя должно быть не короче 2 символов.")
        return value

    def validate_phone(self, value):
        return validate_phone_value(value)

    def validate_password2(self, value):
        # на уровне поля: чтобы при нескольких ошибках «пароли не совпали» тоже попали в fields
        if (self.initial_data.get("password") or "") != value:
            raise serializers.ValidationError("Пароли не совпадают.")
        return value

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password2"):
            raise serializers.ValidationError({"password2": "Пароли не совпадают."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        from apps.products.services import create_seller

        email = validated_data["email"]
        try:
            user = User.objects.create_user(
                email=email,
                password=validated_data["password"],
                first_name=validated_data["first_name"],
                last_name=(validated_data.get("last_name") or "").strip(),
                phone=validated_data.get("phone") or "",
            )
        except IntegrityError as exc:  # гонка двух регистраций
            raise serializers.ValidationError({"email": "Пользователь с таким email уже зарегистрирован."}) from exc

        # Магазин создаётся автоматически (§0.1 ТЗ): shop_name или «<имя> — магазин».
        shop_name = (validated_data.get("shop_name") or "").strip() or f"{user.first_name} — магазин"
        create_seller(owner=user, name=shop_name)
        return user


class LoginSerializer(serializers.Serializer):
    """POST /auth/login/: email + пароль. Ошибка — 401 с общим текстом (не раскрываем, что именно)."""

    email = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip().lower()
        password = attrs.get("password") or ""
        user = None
        if email:
            try:
                candidate = User.objects.get(email__iexact=email)
            except User.DoesNotExist:
                candidate = None
            except User.MultipleObjectsReturned:
                candidate = None
            if candidate is not None and candidate.check_password(password) and candidate.is_active:
                user = candidate
        if user is None:
            raise exceptions.AuthenticationFailed(
                "Неверный email или пароль. Проверьте раскладку или зарегистрируйтесь."
            )
        attrs["user"] = user
        return attrs


class MeUpdateSerializer(serializers.ModelSerializer):
    """PATCH /auth/me/: частичное обновление профиля."""

    email = serializers.CharField(max_length=254, required=False)
    first_name = serializers.CharField(max_length=60, required=False)
    last_name = serializers.CharField(max_length=60, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone"]

    def validate_email(self, value):
        value = validate_email_value(value)
        qs = User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Пользователь с таким email уже зарегистрирован.")
        return value

    def validate_first_name(self, value):
        value = (value or "").strip()
        if len(value) < 2:
            raise serializers.ValidationError("Имя должно быть не короче 2 символов.")
        return value

    def validate_phone(self, value):
        return validate_phone_value(value)

    def update(self, instance, validated_data):
        instance.email = validated_data.get("email", instance.email).lower()
        instance.first_name = validated_data.get("first_name", instance.first_name).strip()
        instance.last_name = (validated_data.get("last_name", instance.last_name) or "").strip()
        instance.phone = validated_data.get("phone", instance.phone) or ""
        instance.save(update_fields=["email", "first_name", "last_name", "phone"])
        return instance


class PasswordSerializer(serializers.Serializer):
    """POST /auth/password/: {current, next}. next ≥ 8, прочие сессии инвалидируются."""

    current = serializers.CharField()
    next = serializers.CharField()

    def validate_next(self, value):
        if len(value or "") < PASSWORD_MIN:
            raise serializers.ValidationError(f"Новый пароль должен быть не короче {PASSWORD_MIN} символов.")
        return value

    def validate(self, attrs):
        if not self.context["request"].user.check_password(attrs.get("current") or ""):
            raise serializers.ValidationError({"current": "Текущий пароль указан неверно."})
        return attrs
