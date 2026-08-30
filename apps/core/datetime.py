"""Общие вещи контракта API: дата-время ISO с миллисекундами и «Z».

Фронтенд парсит даты через `Date.parse` — формат из ТЗ:
`2026-08-30T17:00:59.673Z` (ISO-8601, UTC, обязательно `Z`).
Стандартный `DateTimeField` DRF отдаёт `+00:00` без миллисекунд — делаем как в контракте.
"""

from datetime import UTC

from django.utils import timezone
from rest_framework import serializers

UTC = UTC


def iso_utc(value) -> str | None:
    """datetime → '2026-08-30T17:00:59.673Z' (миллисекунды всегда, Z вместо +00:00)."""
    if value is None:
        return None
    if timezone.is_aware(value):
        value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


class IsoDateTimeField(serializers.Field):
    """DRF-поле: любой datetime в JSON уходит в формате контракта."""

    def to_representation(self, value):
        return iso_utc(value)

    def to_internal_value(self, data):
        raise serializers.ValidationError("Поле только для чтения (даты ставит сервер).")
