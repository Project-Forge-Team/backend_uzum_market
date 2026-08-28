"""Наполнение БД демо-данными.

Флаги:
  --force         пересоздать товары, даже если они уже есть
  --fix-encoding  разово прогнать починку «битой» кодировки (см. ниже)

Раньше исправление кодировки запускалось ВСЕГДА, то есть на каждый деплой в build.sh
это был полный скан всей таблицы товаров (на 20k строк ~1 с и вся таблица в памяти,
на 1M — минуты). Починка данных — разовая операция, она не должна жить в цикле деплоя.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.products.models import Category, Product, Seller

CATEGORIES = [
    {"name": "Электроника", "slug": "electronics"},
    {"name": "Одежда", "slug": "clothing"},
    {"name": "Дом и сад", "slug": "home-garden"},
    {"name": "Красота", "slug": "beauty"},
    {"name": "Спорт", "slug": "sport"},
]

SELLERS = [
    {"name": "Uzum Market Official", "rating": "4.80", "reviews_count": 1520},
    {"name": "TechStore", "rating": "4.50", "reviews_count": 340},
    {"name": "FashionHub", "rating": "4.70", "reviews_count": 890},
    {"name": "HomeComfort", "rating": "4.30", "reviews_count": 210},
]

PRODUCTS = [
    {
        "title": "Беспроводные наушники Apple AirPods Pro 2, MagSafe Type-C",
        "description": (
            "Наушники AirPods Pro 2 с активным шумоподавлением до 2 раз эффективнее. "
            "Режим прозрачности позволяет слышать окружающий мир."
        ),
        "price": "3190000.00",
        "old_price": "3600000.00",
        "rating": "4.95",
        "reviews_count": 450,
        "monthly_payment": "265833.00",
        "delivery_time": "1 день",
        "image": "https://picsum.photos/seed/airpods/600/600",
        "images": [
            "https://picsum.photos/seed/airpods1/600/600",
            "https://picsum.photos/seed/airpods2/600/600",
        ],
        "characteristics": {
            "Время работы": "До 6 часов",
            "Разъём зарядки": "USB Type-C",
            "Шумоподавление": "Активное (ANC)",
            "Тип подключения": "Беспроводное Bluetooth 5.3",
        },
        "is_ad": True,
        "category_slug": "electronics",
        "seller_name": "TechStore",
    },
    {
        "title": "Смартфон Samsung Galaxy A55 5G 8/256GB",
        "description": 'Смартфон Samsung Galaxy A55 с поддержкой 5G. Экран Super AMOLED 6.6" 120Hz.',
        "price": "4990000.00",
        "old_price": "5500000.00",
        "rating": "4.80",
        "reviews_count": 320,
        "monthly_payment": "415833.00",
        "delivery_time": "1-2 дня",
        "image": "https://picsum.photos/seed/a55/600/600",
        "images": ["https://picsum.photos/seed/a551/600/600", "https://picsum.photos/seed/a552/600/600"],
        "characteristics": {
            "Экран": '6.6" Super AMOLED 120Hz',
            "Память": "8/256GB",
            "Камера": "50+12+5 Мп",
            "Батарея": "5000 мАч",
        },
        "is_ad": True,
        "category_slug": "electronics",
        "seller_name": "Uzum Market Official",
    },
    {
        "title": "Куртка зимняя мужская пуховик оверсайз",
        "description": "Тёплая зимняя куртка с натуральным пухом. Водоотталкивающая ткань.",
        "price": "890000.00",
        "old_price": "1200000.00",
        "rating": "4.60",
        "reviews_count": 180,
        "monthly_payment": "74166.00",
        "delivery_time": "2-3 дня",
        "image": "https://picsum.photos/seed/jacket/600/600",
        "images": ["https://picsum.photos/seed/jacket1/600/600"],
        "characteristics": {
            "Сезон": "Зима",
            "Наполнитель": "Натуральный пух",
            "Температурный режим": "до -25°C",
        },
        "is_ad": False,
        "category_slug": "clothing",
        "seller_name": "FashionHub",
    },
    {
        "title": "Робот-пылесос Xiaomi Robot Vacuum S20+",
        "description": "Робот-пылесос Xiaomi с лидарной навигацией. Влажная уборка.",
        "price": "2150000.00",
        "old_price": None,
        "rating": "4.70",
        "reviews_count": 240,
        "monthly_payment": "179166.00",
        "delivery_time": "1-3 дня",
        "image": "https://picsum.photos/seed/vacuum/600/600",
        "images": ["https://picsum.photos/seed/vacuum1/600/600"],
        "characteristics": {
            "Тип уборки": "Сухая и влажная",
            "Навигация": "Лидар",
            "Время работы": "до 130 минут",
        },
        "is_ad": False,
        "category_slug": "home-garden",
        "seller_name": "HomeComfort",
    },
    {
        "title": "Кроссовки Nike Air Force 1 '07",
        "description": "Классические кроссовки Nike Air Force 1. Верх из натуральной кожи.",
        "price": "1290000.00",
        "old_price": "1490000.00",
        "rating": "4.90",
        "reviews_count": 560,
        "monthly_payment": "107500.00",
        "delivery_time": "2-4 дня",
        "image": "https://picsum.photos/seed/nike/600/600",
        "images": ["https://picsum.photos/seed/nike1/600/600", "https://picsum.photos/seed/nike2/600/600"],
        "characteristics": {
            "Верх": "Натуральная кожа",
            "Амортизация": "Air",
            "Подошва": "Резина",
        },
        "is_ad": True,
        "category_slug": "sport",
        "seller_name": "FashionHub",
    },
    {
        "title": "Фен Dyson Supersonic HD08",
        "description": "Фен Dyson Supersonic с цифровым мотором V9. Ионизация.",
        "price": "3490000.00",
        "old_price": "3990000.00",
        "rating": "4.85",
        "reviews_count": 190,
        "monthly_payment": "290833.00",
        "delivery_time": "1-2 дня",
        "image": "https://picsum.photos/seed/dyson/600/600",
        "images": ["https://picsum.photos/seed/dyson1/600/600"],
        "characteristics": {
            "Мощность": "1600 Вт",
            "Мотор": "Цифровой V9",
            "Ионизация": "Да",
        },
        "is_ad": False,
        "category_slug": "beauty",
        "seller_name": "Uzum Market Official",
    },
]


def fix_mojibake(value):
    """UTF-8 байты, прочитанные как Latin-1 → обратно в нормальный текст.

    Возвращает (исправлено_или_нет, значение). Строку, которую нельзя декодировать
    как latin-1, не трогаем: это уже нормальный текст.
    """
    if not isinstance(value, str) or not value:
        return False, value
    try:
        fixed = value.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return False, value
    return (fixed != value), fixed


class Command(BaseCommand):
    help = "Заполняет БД демо-данными (категории, продавцы, товары)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Залить данные даже если товары уже есть")
        parser.add_argument("--fix-encoding", action="store_true", help="Разово починить битую кодировку в текстах")
        parser.add_argument("--reset", action="store_true", help="Удалить демо-данные перед заполнением")

    def handle(self, *args, **options):
        if options["fix_encoding"]:
            self._fix_encoding()

        if not options["force"] and Product.objects.exists():
            self.stdout.write(self.style.WARNING("Товары уже есть — пропуск (используйте --force)."))
            return

        with transaction.atomic():
            if options["reset"]:
                Product.objects.all().delete()
                Category.objects.all().delete()
                Seller.objects.all().delete()
                self.stdout.write("Старые данные удалены.")

            categories = {
                row["slug"]: Category.objects.get_or_create(slug=row["slug"], defaults=row)[0] for row in CATEGORIES
            }
            sellers = {
                row["name"]: Seller.objects.update_or_create(name=row["name"], defaults=row)[0] for row in SELLERS
            }

            created = 0
            for payload in PRODUCTS:
                data = dict(payload)
                slug = data.pop("category_slug")
                seller_name = data.pop("seller_name")
                _, was_created = Product.objects.get_or_create(
                    title=data["title"],
                    defaults={**data, "category": categories.get(slug), "seller": sellers.get(seller_name)},
                )
                created += int(was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed завершён: товаров создано {created}, категорий {len(categories)}, продавцов {len(sellers)}."
            )
        )

    def _fix_encoding(self):
        """Однократная починка, а не «на каждый деплой». Только --fix-encoding."""
        text_fields = ["title", "description", "delivery_time"]
        fixed_products = 0
        # iterator(): не держим всю таблицу в памяти
        for product in Product.objects.only(*text_fields, "characteristics").iterator(chunk_size=2000):
            changed = False
            for field in text_fields:
                was_fixed, value = fix_mojibake(getattr(product, field))
                if was_fixed:
                    setattr(product, field, value)
                    changed = True
            if isinstance(product.characteristics, dict):
                new_chars = {}
                for key, val in product.characteristics.items():
                    _, new_key = fix_mojibake(key)
                    _, new_val = fix_mojibake(val)
                    new_chars[new_key] = new_val
                if new_chars != product.characteristics:
                    product.characteristics = new_chars
                    changed = True
            if changed:
                product.save(update_fields=[*text_fields, "characteristics"])
                fixed_products += 1

        for model, fields in ((Category, ["name"]), (Seller, ["name"])):
            for obj in model.objects.all():
                changed = False
                for field in fields:
                    was_fixed, value = fix_mojibake(getattr(obj, field))
                    if was_fixed:
                        setattr(obj, field, value)
                        changed = True
                if changed:
                    obj.save(update_fields=fields)
                    fixed_products += 1

        self.stdout.write(self.style.SUCCESS(f"Кодировка: исправлено объектов — {fixed_products}."))
