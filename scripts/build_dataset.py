import json

with open('scripts/products_data.json', encoding='utf-8') as f:
    raw_products = json.load(f)

seller_map = {
    1: 'uzum-students',
    2: 'electro-house',
    3: 'techno-plus',
    4: 'smart-house',
    5: 'gadget-zone',
    6: 'home-and-garden',
    7: 'sport-line',
    8: 'book-world',
    9: 'beauty-uz',
    10: 'kids-planet'
}

category_map = {
    1: 'elektronika',
    2: 'bytovaya-tehnika',
    3: 'odezhda',
    4: 'obuv',
    5: 'krasota',
    6: 'sport',
    7: 'dom-i-sad',
    8: 'knigi',
    9: 'detyam',
    10: 'produkty'
}

def py_repr(val):
    if val is None:
        return 'None'
    if val is True:
        return 'True'
    if val is False:
        return 'False'
    if isinstance(val, (int, float)):
        return repr(val)
    if isinstance(val, str):
        return repr(val)
    if isinstance(val, list):
        return '[' + ', '.join(py_repr(x) for x in val) + ']'
    if isinstance(val, tuple):
        return '(' + ', '.join(py_repr(x) for x in val) + ')'
    if isinstance(val, dict):
        return '{' + ', '.join(f'{py_repr(k)}: {py_repr(v)}' for k, v in val.items()) + '}'
    return repr(val)

products_code = 'PRODUCTS = [\n'
for i, p in enumerate(raw_products):
    seller_slug = seller_map[p['seller_id']]
    cat_slug = category_map[p['category_id']]
    title = p['title']
    brand = p.get('brand', 'Без бренда')
    price = p['price']
    old_price = p.get('old_price')
    stock = p.get('stock', 20)
    is_ad = p.get('is_ad', i % 5 == 0)
    delivery = p.get('delivery_time', 'Завтра')
    chars = p.get('characteristics', {})
    images = p.get('images', [])
    desc = p.get('description', f'{title} высокого качества.')
    days_ago = 10 + (i * 2) % 60
    
    products_code += f'    (\n'
    products_code += f'        {py_repr(seller_slug)},\n'
    products_code += f'        {py_repr(title)},\n'
    products_code += f'        {py_repr(cat_slug)},\n'
    products_code += f'        {py_repr(brand)},\n'
    products_code += f'        {price},\n'
    products_code += f'        {py_repr(old_price)},\n'
    products_code += f'        {stock},\n'
    products_code += f'        {py_repr(is_ad)},\n'
    products_code += f'        {py_repr(delivery)},\n'
    products_code += f'        {py_repr(chars)},\n'
    products_code += f'        {days_ago},\n'
    products_code += f'        {py_repr(images)},\n'
    products_code += f'        {py_repr(desc)},\n'
    products_code += f'    ),\n'
products_code += ']\n'

sample_reviews = [
    ('Азиз Юсупов', 5, 'Отличный товар, всё работает безупречно! Очень доволен покупкой.', 'Качество, быстрая доставка', '', 'Спасибо за доверие к нашему магазину!', True),
    ('Малика Рахимова', 5, 'Прекрасный выбор за свои деньги. Доставили на следующий день.', 'Дизайн, цена', '', None, False),
    ('Дмитрий Ким', 4, 'Хорошее качество, покупкой доволен. Единственное — коробка была слегка помята.', 'Функционал, надежность', 'Упаковка', None, False),
    ('Шахло Умарова', 5, 'Супер! Соответствует описанию на 100%. Буду заказывать ещё.', 'Качество материалов, сборка', '', 'Благодарим за приятный отзыв!', True),
    ('Тимур Алиев', 5, 'Отличная вещь, рекомендую всем к покупке!', 'Удобство, практичность', '', None, False),
    ('Елена Пак', 4, 'В целом всё хорошо, работает как положено.', 'Цена-качество', 'Инструкция', None, False),
    ('Сарвар Хусанов', 5, 'Пользуюсь уже неделю, никаких нареканий. Очень удобный.', 'Надежность', '', None, True),
    ('Нилуфар Асланова', 5, 'Очень понравилось качество, цвет вживую даже лучше, чем на фото.', 'Внешний вид, удобство', '', 'Спасибо за ваш отзыв!', False),
]

reviews_code = '_REVIEWS = {\n'
for i in range(len(raw_products)):
    r1 = sample_reviews[(i * 2) % len(sample_reviews)]
    r2 = sample_reviews[(i * 2 + 1) % len(sample_reviews)]
    reviews_code += f'    {i}: [\n'
    reviews_code += f'        {py_repr(r1)},\n'
    reviews_code += f'        {py_repr(r2)},\n'
    reviews_code += f'    ],\n'
reviews_code += '}\n'

full_content = f'''"""Демо-датасет (§9 ТЗ): 10 категорий, 10 магазинов, 51 товар с реальными фото, 102 отзыва, заказы.

Датасет детерминирован (без RNG). Демо-аккаунты (пароль у всех Password123):
  seller@uzum.uz  — «Uzum Students»
  buyer@uzum.uz   — покупатель
  electro@uzum.uz — «Electro House»
"""

DEMO_PASSWORD = "Password123"  # noqa: S105

CATEGORIES = [
    # name, slug, emoji, color
    ("Электроника", "elektronika", "📱", "#EDE9FF"),
    ("Бытовая техника", "bytovaya-tehnika", "🍳", "#FFF3E0"),
    ("Одежда", "odezhda", "👕", "#E3F2FD"),
    ("Обувь", "obuv", "👟", "#FCE4EC"),
    ("Красота", "krasota", "💄", "#F3E5F5"),
    ("Спорт", "sport", "⚽", "#E8F5E9"),
    ("Дом и сад", "dom-i-sad", "🏡", "#FFF8E1"),
    ("Книги", "knigi", "📚", "#EFEBE9"),
    ("Детям", "detyam", "🧸", "#E0F7FA"),
    ("Продукты", "produkty", "🛒", "#F1F8E9"),
]

SELLERS = [
    # name, slug, city, description, verified
    ("Uzum Students", "uzum-students", "Ташкент", "Студенческий магазин: гаджеты и всё для учёбы с доставкой за день.", True),
    ("Electro House", "electro-house", "Ташкент", "Электроника и умный дом: официальная гарантия, рассрочка 0%.", True),
    ("Techno Plus", "techno-plus", "Ташкент", "Компьютеры, комплектующие и периферия.", False),
    ("Smart House", "smart-house", "Самарканд", "Умные лампы, розетки и датчики для уютного дома.", False),
    ("Gadget Zone", "gadget-zone", "Ташкент", "Наушники, колонки и аксессуары для телефона.", False),
    ("Home & Garden", "home-and-garden", "Бухара", "Всё для дома, сада и кухонных мастерских.", False),
    ("Sport Line", "sport-line", "Ташкент", "Спортивный инвентарь и экипировка.", False),
    ("Book World", "book-world", "Ташкент", "Книги на русском и узбекском, доставка по всей стране.", False),
    ("Beauty UZ", "beauty-uz", "Ташкент", "Косметика и уход от проверенных брендов.", False),
    ("Kids Planet", "kids-planet", "Ташкент", "Игрушки и товары для детей.", False),
]

{products_code}

DRAFT_PRODUCT = (
    "uzum-students",
    "Наушники StudyPod ANC (черновик)",
    "elektronika",
    "StudyPod",
    450_000,
    None,
    10,
    False,
    "Завтра",
    {{"Тип": "накладные", "ANC": "есть", "Автономность": "30 часов"}},
    5,
    [
        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&h=600&fit=crop",
        "https://images.unsplash.com/photo-1484704849700-f032a568e944?w=600&h=600&fit=crop",
    ],
    "Качественные беспроводные накладные наушники с активным шумоподавлением и глубоким басом (черновик).",
)

{reviews_code}

DEMO_ORDERS = [
    {{
        "status": "packing",
        "days_ago": 1,
        "delivery_method": "pickup_point",
        "payment_method": "cash",
        "address": "г. Ташкент, пункт выдачи Uzum № 42 (ул. Навои, 14)",
        "comment": "Просьба упаковать в фирменный пакет",
        "promo_code": None,
        "items": [
            {{"product": 0, "qty": 1}},
            {{"product": 3, "qty": 1}},
        ],
        "events": [("new", 1.0, "Заказ оформлен"), ("packing", 0.96, "Заказ собирается")],
    }},
    {{
        "status": "shipping",
        "days_ago": 4,
        "delivery_method": "courier",
        "payment_method": "installment",
        "address": "г. Ташкент, ул. Амира Темура, 12, кв. 45",
        "comment": "",
        "promo_code": "STUDENT10",
        "items": [
            {{"product": 1, "qty": 1}},
            {{"product": 6, "qty": 2}},
        ],
        "events": [
            ("new", 4.0, "Заказ оформлен"),
            ("packing", 3.9, "Заказ собирается"),
            ("shipping", 3.5, "Заказ собран и передан в доставку"),
        ],
    }},
]

DEMO_USERS = [
    # email, first_name, last_name, phone, seller_slug|None
    ("seller@uzum.uz", "Сардор", "Каримов", "+998901112233", "uzum-students"),
    ("buyer@uzum.uz", "Азиз", "Юсупов", "+998901234567", None),
    ("electro@uzum.uz", "Эмир", "Рахимов", "+998905554433", "electro-house"),
    ("techno@uzum.uz", "Тимур", "Алиев", "+998902223344", "techno-plus"),
    ("smart@uzum.uz", "Сарвар", "Хусанов", "+998903334455", "smart-house"),
    ("gadget@uzum.uz", "Жасур", "Махмудов", "+998904445566", "gadget-zone"),
    ("home@uzum.uz", "Фаррух", "Ибрагимов", "+998906667788", "home-and-garden"),
    ("sport@uzum.uz", "Даврон", "Рустамов", "+998907778899", "sport-line"),
    ("book@uzum.uz", "Нодир", "Шарипов", "+998908889900", "book-world"),
    ("beauty@uzum.uz", "Шахло", "Умарова", "+998909990011", "beauty-uz"),
    ("kids@uzum.uz", "Малика", "Каримова", "+998900001122", "kids-planet"),
]

PROMO_CODES = [
    # code, percent, min_subtotal, label
    ("STUDENT10", 10, 200_000, "Учебный промокод: −10%"),
    ("UZUM2026", 5, 0, "Знакомство с маркетплейсом: −5%"),
]


def reviews() -> dict[int, list]:
    return _REVIEWS
'''

with open('apps/products/dataset.py', 'w', encoding='utf-8') as f:
    f.write(full_content)

print('Generated apps/products/dataset.py successfully with proper Python repr!')

