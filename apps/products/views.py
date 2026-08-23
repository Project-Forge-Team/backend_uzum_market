from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters

from .models import Product, Category, Seller
from .serializers import ProductSerializer, CategorySerializer, SellerSerializer


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Категории: список и детали."""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class SellerViewSet(viewsets.ReadOnlyModelViewSet):
    """Продавцы: список и детали."""
    queryset = Seller.objects.all()
    serializer_class = SellerSerializer


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Товары: список (с фильтрами, поиском, сортировкой) и детали."""
    queryset = Product.objects.select_related('category', 'seller').all()
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'seller']
    search_fields = ['title', 'description']
    ordering_fields = ['price', 'rating', 'created_at']
    ordering = ['-created_at']