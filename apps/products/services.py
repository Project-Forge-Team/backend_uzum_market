"""Бизнес-логика каталога: магазины, слаги, денормализация отзывов, видимость."""

from django.db import transaction
from django.db.models import Avg, Count

from .models import Product, Review, Seller
from .translit import unique_slug

SHOP_MIN_NAME = 3
SHOP_MAX_NAME = 60


class ShopCreationError(ValueError):
    def __init__(self, message: str, field: str = "name"):
        super().__init__(message)
        self.field = field


def create_seller(owner, name: str, city: str = "Ташкент", description: str = "") -> Seller:
    """Создание магазина с валидацией имени и уникальным стабильным слагом."""
    name = (name or "").strip()
    if not (SHOP_MIN_NAME <= len(name) <= SHOP_MAX_NAME):
        raise ShopCreationError(f"Название магазина должно быть от {SHOP_MIN_NAME} до {SHOP_MAX_NAME} символов.")
    return Seller.objects.create(
        name=name,
        slug=unique_slug(Seller, name, max_length=80),
        city=(city or "Ташкент").strip() or "Ташкент",
        description=(description or "").strip(),
        owner=owner,
    )


@transaction.atomic
def upsert_review(product: Product, user, rating: int, text: str, pros: str = "", cons: str = ""):
    """Один отзыв на (товар, пользователь): повторный POST = редактирование (§4 ТЗ).

    Гонка двух вкладок не создаёт дубль: при IntegrityError обновляем существующую строку.
    Возвращает (review, created).
    """
    author = f"{user.first_name} {user.last_name}".strip() or user.email
    verified = review_verified_flag(user, product)
    review, created = Review.objects.get_or_create(
        product=product,
        user=user,
        defaults={"author": author, "rating": rating, "text": text, "pros": pros, "cons": cons, "verified": verified},
    )
    if not created:
        review.author = author
        review.rating = rating
        review.text = text
        review.pros = pros
        review.cons = cons
        review.verified = verified
        review.save(update_fields=["author", "rating", "text", "pros", "cons", "verified", "updated_at"])
    recompute_product_reviews(product)
    return review, created


def review_verified_flag(user, product) -> bool:
    """verified = есть не-отменённый заказ с этим товаром у автора (§2 ТЗ)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    from apps.orders.models import Order, OrderItem  # локальный импорт: без цикла apps.orders→products

    return (
        OrderItem.objects.filter(product=product, order__user=user)
        .exclude(order__status=Order.Status.CANCELLED)
        .exists()
    )


def recompute_product_reviews(product: Product) -> None:
    """rating / reviews_count / rating_breakdown товара + рейтинг магазина (§8 ТЗ)."""
    stats = list(product.reviews.values("rating").annotate(n=Count("id")).order_by("-rating"))
    by_stars = {row["rating"]: row["n"] for row in stats}
    total = sum(by_stars.values())
    avg = product.reviews.aggregate(a=Avg("rating"))["a"] or 0
    product.rating = round(avg, 2)
    product.reviews_count = total
    product.rating_breakdown = [{"stars": stars, "count": by_stars.get(stars, 0)} for stars in (5, 4, 3, 2, 1)]
    product.save(update_fields=["rating", "reviews_count", "rating_breakdown", "updated_at"])
    if product.seller_id:
        recompute_seller_reviews(product.seller)


def recompute_seller_reviews(seller: Seller) -> None:
    stats = Review.objects.filter(product__seller=seller).aggregate(avg=Avg("rating"), total=Count("id"))
    seller.rating = round(stats["avg"] or 0, 2)
    seller.reviews_count = stats["total"] or 0
    seller.save(update_fields=["rating", "reviews_count"])


def active_seller_product_counts() -> dict[int, int]:
    """seller_id → число активных товаров (для встраивания продавца в карточки)."""
    rows = (
        Product.objects.filter(status=Product.Status.ACTIVE)
        .values("seller")
        .annotate(n=Count("id"))
        .values_list("seller", "n")
    )
    return dict(rows)


def owns_product(user, product) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    shop = getattr(user, "shop", None)
    return product.seller_id is not None and shop is not None and shop.pk == product.seller_id
