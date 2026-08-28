from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Профиль пользователя (чтение)."""

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "date_joined"]
        read_only_fields = ["id", "date_joined"]


class RegisterSerializer(serializers.ModelSerializer):
    """Регистрация: email + password (с валидацией парольных политик Django)."""

    email = serializers.EmailField(
        required=True,
        trim_whitespace=True,
        error_messages={"unique": "Пользователь с таким email уже существует."},
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="Пользователь с таким email уже существует.",
                lookup="iexact",
            )
        ],
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Минимум 8 символов, не только цифры, не совпадает с email.",
    )
    password2 = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        label="Подтверждение пароля",
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone", "password", "password2"]

    def validate_email(self, value):
        return value.strip().lower()

    def validate_password(self, value):
        # Валидатор на поле не дошёл бы до контекста пользователя — делаем явно.
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password2"):
            raise serializers.ValidationError({"password2": "Пароли не совпадают."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("password2", None)
        try:
            return User.objects.create_user(**validated_data)
        except IntegrityError as exc:
            # Гонка двух параллельных регистраций: exists()/unique разошлись.
            raise serializers.ValidationError({"email": "Пользователь с таким email уже существует."}) from exc


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Логин по email: приводим ввод к тому же виду, что хранится (strip + lower)."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        return token

    def validate(self, attrs):
        email = (attrs.get(self.username_field) or "").strip()
        attrs[self.username_field] = email.lower()
        return super().validate(attrs)
