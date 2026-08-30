"""Envelope-пагинация контракта (§1.1 ТЗ).

Стандартный DRF-конверт не подходит: `next`/`previous` у нас — **boolean**, не URL.
Списки, которые фронт не просит постранично, отдают тот же конверт с total_pages=1.
"""

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class EnvelopePagination(PageNumberPagination):
    """`/api/products/` — с query-параметрами page / page_size (4..120, дефолт 20)."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 120
    min_page_size = 4

    def get_page_size(self, request):
        try:
            size = int(request.query_params[self.page_size_query_param])
        except (KeyError, TypeError, ValueError):
            return self.page_size
        return max(self.min_page_size, min(size, self.max_page_size))

    def get_paginated_response(self, data):
        return Response(self.envelope(self.page, data))

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
                "total_pages": {"type": "integer"},
                "next": {"type": "boolean"},
                "previous": {"type": "boolean"},
                "results": schema,
            },
        }

    @staticmethod
    def envelope(page, data, count=None):
        """Общий конверт: используется и пагинацией, и «непагинируемыми» списками."""
        count = page.paginator.count if count is None else count
        return {
            "count": count,
            "page": page.number,
            "page_size": page.paginator.per_page,
            "total_pages": page.paginator.num_pages,
            "next": page.has_next(),
            "previous": page.has_previous(),
            "results": data,
        }

    @staticmethod
    def whole_list(items: list) -> dict:
        """Конверт для списка «без пагинации»: всё содержимое, одна страница (§1.1)."""
        return {
            "count": len(items),
            "page": 1,
            "page_size": len(items) or 1,
            "total_pages": 1,
            "next": False,
            "previous": False,
            "results": items,
        }
