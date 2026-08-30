"""Совместимость: троттлинг переехал в apps.core.throttling."""

from apps.core.throttling import ScopedIpThrottle, ScopedUserOrIpThrottle, client_ip  # noqa: F401

ProxyAwareScopedRateThrottle = ScopedIpThrottle
