from django.db import models

# Create your models here.
# 1. Отдельная модель Продавца
class Seller(models.Model):
    name = models.CharField(max_length=255)
    rating = models.FloatField(default=0.0)
    reviews_count = models.PositiveIntegerField(default=0)

# 2. Отдельная модель Категории
class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

# 3. Основная модель Товара (ссылается на остальные)
class Product(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    old_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    rating = models.FloatField(default=0.0)
    reviews_count = models.PositiveIntegerField(default=0)
    monthly_payment = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    delivery_time = models.CharField(max_length=100)
    image = models.ImageField(upload_to='products/')
    images = models.JSONField(default=list)  # или отдельная модель ProductImage
    characteristics = models.JSONField(default=dict)
    is_ad = models.BooleanField(default=False)
    
    # Связи с другими моделями
    seller = models.ForeignKey(Seller, on_delete=models.SET_NULL, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)