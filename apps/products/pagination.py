from django.conf import settings
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class CatalogPagination(PageNumberPagination):
    """Пагинация с управляемым размером страницы.

    Было: жёсткий `PAGE_SIZE = 10`, а `?page_size=50` из API.md молча игнорировался —
    фронт дёргал по 10 товаров сотнями запросов. Теперь параметр работает, но с потолком,
    чтобы `?page_size=100000` не уложил сервер.
    """

    page_size = settings.PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = settings.PAGE_SIZE_MAX

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "page_size": self.get_page_size(self.request),
                "total_pages": self.page.paginator.num_pages,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )
