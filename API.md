# API документация для frontend

Ниже описан API, к которому будет обращаться frontend в текущем backend-проекте.

## Базовый URL

- Локально: `http://localhost:8000/api`
- Главный роутер подключён в [config/urls.py](config/urls.py)

## Список доступных endpoint-ов

### 1) Получить список товаров

- Метод: `GET`
- URL: `/api/products/`
- Описание: возвращает список всех товаров

Пример запроса:

```http
GET http://localhost:8000/api/products/
```

Пример ответа:

```json
[
  {
    "id": 1,
    "title": "Смартфон X",
    "description": "Описание товара",
    "price": "999.99",
    "old_price": "1200.00",
    "rating": 4.8,
    "reviews_count": 120,
    "monthly_payment": "45.00",
    "delivery_time": "2-3 дня",
    "image": "http://localhost:8000/media/products/phone.jpg",
    "images": [
      "http://localhost:8000/media/products/phone_1.jpg",
      "http://localhost:8000/media/products/phone_2.jpg"
    ],
    "characteristics": {
      "color": "black",
      "memory": "128GB",
      "battery": "5000mAh"
    },
    "is_ad": false,
    "seller": {
      "id": 1,
      "name": "Seller Name",
      "rating": 4.9,
      "reviews_count": 250
    },
    "category": {
      "id": 1,
      "name": "Phones",
      "slug": "phones"
    }
  }
]
```

---

### 2) Получить товар по ID

- Метод: `GET`
- URL: `/api/products/{id}/`
- Описание: возвращает конкретный товар по идентификатору

Пример запроса:

```http
GET http://localhost:8000/api/products/1/
```

Пример ответа:

```json
{
  "id": 1,
  "title": "Смартфон X",
  "description": "Описание товара",
  "price": "999.99",
  "old_price": "1200.00",
  "rating": 4.8,
  "reviews_count": 120,
  "monthly_payment": "45.00",
  "delivery_time": "2-3 дня",
  "image": "http://localhost:8000/media/products/phone.jpg",
  "images": [
    "http://localhost:8000/media/products/phone_1.jpg",
    "http://localhost:8000/media/products/phone_2.jpg"
  ],
  "characteristics": {
    "color": "black",
    "memory": "128GB",
    "battery": "5000mAh"
  },
  "is_ad": false,
  "seller": {
    "id": 1,
    "name": "Seller Name",
    "rating": 4.9,
    "reviews_count": 250
  },
  "category": {
    "id": 1,
    "name": "Phones",
    "slug": "phones"
  }
}
```

---

## Структура данных товара

### Product

| Поле              | Тип         | Описание                       |
| ----------------- | ----------- | ------------------------------ |
| `id`              | integer     | ID товара                      |
| `title`           | string      | Название товара                |
| `description`     | string      | Описание товара                |
| `price`           | string      | Цена товара                    |
| `old_price`       | string/null | Старая цена                    |
| `rating`          | float       | Рейтинг товара                 |
| `reviews_count`   | integer     | Количество отзывов             |
| `monthly_payment` | string/null | Оплата в рассрочку             |
| `delivery_time`   | string      | Время доставки                 |
| `image`           | string      | Главная картинка               |
| `images`          | array       | Список дополнительных картинок |
| `characteristics` | object      | Характеристики товара          |
| `is_ad`           | boolean     | Является рекламным объявлением |
| `seller`          | object      | Данные продавца                |
| `category`        | object      | Данные категории               |

### Seller

| Поле            | Тип     | Описание                    |
| --------------- | ------- | --------------------------- |
| `id`            | integer | ID продавца                 |
| `name`          | string  | Имя продавца                |
| `rating`        | float   | Рейтинг продавца            |
| `reviews_count` | integer | Количество отзывов продавца |

### Category

| Поле   | Тип     | Описание           |
| ------ | ------- | ------------------ |
| `id`   | integer | ID категории       |
| `name` | string  | Название категории |
| `slug` | string  | URL-friendly slug  |

---

## HTTP статусы

- `200 OK` — успешный запрос
- `404 Not Found` — товар не найден
- `500 Internal Server Error` — ошибка сервера

---

## Важно для frontend

В текущей реализации backend уже готов для работы с продуктами, и фронтенд может использовать следующий сценарий:

1. Получить список товаров: `GET /api/products/`
2. Отобразить карточки товаров
3. При клике открыть детальную страницу товара: `GET /api/products/{id}/`

> В текущем состоянии API для `Category` и `Seller` как отдельных независимых маршрутов нет. Они приходят вложенно внутри объекта товара.

---

## Примечание по дальнейшему развитию

Если нужно, можно добавить отдельные endpoints для:

- `GET /api/categories/`
- `GET /api/sellers/`
- `GET /api/products/?category=phones`
- `POST /api/products/` для создания товара
- `PUT/PATCH /api/products/{id}/` для обновления

Но сейчас базовый рабочий контракт для frontend — это именно:

```text
GET /api/products/
GET /api/products/{id}/
```
