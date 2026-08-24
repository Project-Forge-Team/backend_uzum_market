from django.core.management.base import BaseCommand
from django.db import IntegrityError

from apps.products.models import Category, Seller, Product


class Command(BaseCommand):
    help = 'Заполняет БД тестовыми данными (категории, продавцы, товары)'

    def handle(self, *args, **options):
        # Если товары уже есть — пропускаем
        if Product.objects.exists():
            self.stdout.write(self.style.WARNING('Данные уже существуют — пропуск.'))
            return

        # --- Категории ---
        categories_data = [
            {'name': 'Электроника', 'slug': 'electronics'},
            {'name': 'Одежда', 'slug': 'clothing'},
            {'name': 'Дом и сад', 'slug': 'home-garden'},
            {'name': 'Красота', 'slug': 'beauty'},
            {'name': 'Спорт', 'slug': 'sport'},
        ]
        categories = {}
        for cd in categories_data:
            cat = Category.objects.create(**cd)
            categories[cat.slug] = cat
        self.stdout.write(f'Создано категорий: {len(categories)}')

        # --- Продавцы ---
        sellers_data = [
            {'name': 'Uzum Market Official', 'rating': 4.8, 'reviews_count': 1520},
            {'name': 'TechStore', 'rating': 4.5, 'reviews_count': 340},
            {'name': 'FashionHub', 'rating': 4.7, 'reviews_count': 890},
            {'name': 'HomeComfort', 'rating': 4.3, 'reviews_count': 210},
        ]
        sellers = {s['name']: Seller.objects.create(**s) for s in sellers_data}
        self.stdout.write(f'Создано продавцов: {len(sellers)}')

        # --- Товары ---
        products_data = [
            {
                'title': 'Беспроводные наушники Apple AirPods Pro 2, MagSafe Type-C',
                'description': 'Наушники AirPods Pro 2 с активным шумоподавлением до 2 раза эффективнее. Режим прозрачности позволяет слышать окружающий мир. Акустический уплотнитель обеспечивает идеальную посадку.',
                'price': '3190000.00', 'old_price': '3600000.00',
                'rating': 4.95, 'reviews_count': 450,
                'monthly_payment': '265833.00', 'delivery_time': '1 день',
                'images': [
                    'https://picsum.photos/600/600?random=11',
                    'https://picsum.photos/600/600?random=12',
                    'https://picsum.photos/600/600?random=13',
                ],
                'characteristics': {
                    'Время работы': 'До 6 часов',
                    'Разъём зарядки': 'USB Type-C',
                    'Шумоподавление': 'Активное (ANC)',
                    'Тип подключения': 'Беспроводное Bluetooth 5.3',
                },
                'is_ad': True,
                'category_slug': 'electronics', 'seller_name': 'TechStore',
            },
            {
                'title': 'Смартфон Samsung Galaxy A55 5G 8/256GB',
                'description': 'Смартфон Samsung Galaxy A55 с поддержкой 5G. Экран Super AMOLED 6.6" 120Hz. Тройная камера 50+12+5 Мп. Процессор Exynos 1480.',
                'price': '4990000.00', 'old_price': '5500000.00',
                'rating': 4.8, 'reviews_count': 320,
                'monthly_payment': '415833.00', 'delivery_time': '1-2 дня',
                'images': [
                    'https://picsum.photos/600/600?random=21',
                    'https://picsum.photos/600/600?random=22',
                ],
                'characteristics': {
                    'Экран': '6.6" Super AMOLED 120Hz',
                    'Память': '8/256GB',
                    'Камера': '50+12+5 Мп',
                    'Батарея': '5000 мАч',
                },
                'is_ad': True,
                'category_slug': 'electronics', 'seller_name': 'Uzum Market Official',
            },
            {
                'title': 'Куртка зимняя мужская пуховик оверсайз',
                'description': 'Тёплая зимняя куртка с натуральным пухом. Водоотталкивающая ткань. Капюшон с меховой оторочкой. Температурный режим до -25°C.',
                'price': '890000.00', 'old_price': '1200000.00',
                'rating': 4.6, 'reviews_count': 180,
                'monthly_payment': '74166.00', 'delivery_time': '2-3 дня',
                'images': [
                    'https://picsum.photos/600/600?random=31',
                    'https://picsum.photos/600/600?random=32',
                ],
                'characteristics': {
                    'Сезон': 'Зима',
                    'Наполнитель': 'Натуральный пух',
                    'Температурный режим': 'до -25°C',
                    'Капюшон': 'Да, с меховой оторочкой',
                },
                'is_ad': False,
                'category_slug': 'clothing', 'seller_name': 'FashionHub',
            },
            {
                'title': 'Робот-пылесос Xiaomi Robot Vacuum S20+',
                'description': 'Робот-пылесос Xiaomi с лидарной навигацией. Влажная уборка. Время работы до 130 минут. Управление через приложение Mi Home.',
                'price': '2150000.00', 'old_price': None,
                'rating': 4.7, 'reviews_count': 240,
                'monthly_payment': '179166.00', 'delivery_time': '1-3 дня',
                'images': [
                    'https://picsum.photos/600/600?random=41',
                    'https://picsum.photos/600/600?random=42',
                ],
                'characteristics': {
                    'Тип уборки': 'Сухая и влажная',
                    'Навигация': 'Лидар',
                    'Время работы': 'до 130 минут',
                    'Управление': 'Приложение Mi Home',
                },
                'is_ad': False,
                'category_slug': 'home-garden', 'seller_name': 'HomeComfort',
            },
            {
                'title': 'Кроссовки Nike Air Force 1 \'07',
                'description': 'Классические кроссовки Nike Air Force 1. Верх из натуральной кожи. Амортизация Air. Подошва из резины с круговым узором протектора.',
                'price': '1290000.00', 'old_price': '1490000.00',
                'rating': 4.9, 'reviews_count': 560,
                'monthly_payment': '107500.00', 'delivery_time': '2-4 дня',
                'images': [
                    'https://picsum.photos/600/600?random=51',
                    'https://picsum.photos/600/600?random=52',
                    'https://picsum.photos/600/600?random=53',
                ],
                'characteristics': {
                    'Верх': 'Натуральная кожа',
                    'Амортизация': 'Air',
                    'Подошва': 'Резина',
                    'Назначение': 'Повседневные',
                },
                'is_ad': True,
                'category_slug': 'sport', 'seller_name': 'FashionHub',
            },
            {
                'title': 'Фен Dyson Supersonic HD08',
                'description': 'Фен Dyson Supersonic с цифровым мотором V9. Ионизация. Три настройки скорости, четыре режима нагрева. Магнитные насадки в комплекте.',
                'price': '3490000.00', 'old_price': '3990000.00',
                'rating': 4.85, 'reviews_count': 190,
                'monthly_payment': '290833.00', 'delivery_time': '1-2 дня',
                'images': [
                    'https://picsum.photos/600/600?random=61',
                    'https://picsum.photos/600/600?random=62',
                ],
                'characteristics': {
                    'Мощность': '1600 Вт',
                    'Мотор': 'Цифровой V9',
                    'Ионизация': 'Да',
                    'Насадки': '5 магнитных',
                },
                'is_ad': False,
                'category_slug': 'beauty', 'seller_name': 'Uzum Market Official',
            },
        ]

        for pd in products_data:
            category = categories.get(pd.pop('category_slug'))
            seller = sellers.get(pd.pop('seller_name'))
            Product.objects.create(
                category=category,
                seller=seller,
                image='https://picsum.photos/600/600',
                **pd,
            )

        self.stdout.write(f'Создано товаров: {len(products_data)}')
        self.stdout.write(self.style.SUCCESS('Seed завершён успешно!'))
