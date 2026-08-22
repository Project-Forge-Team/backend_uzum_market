# Uzum Market Clone — API Documentation

> **Статус:** `v1.0.0` · **Формат:** `JSON` · **Кодировка:** `UTF-8`

---

## 📌 Base URL

| Окружение      | URL                                            |
| -------------- | ---------------------------------------------- |
| **Production** | `https://backend-uzum-market.onrender.com/api` |
| **Local**      | `http://127.0.0.1:8000/api`                    |

Все запросы и ответы — строго в формате **JSON**.

| Header         | Значение           |
| -------------- | ------------------ |
| `Content-Type` | `application/json` |
| `Accept`       | `application/json` |

---

## 🔐 Авторизация

На текущем этапе API **не требует авторизации** — все эндпоинты публичные.

> **Примечание:** Если в будущем будет добавлена JWT-аутентификация, токен передаётся так:
>
> ```
> Authorization: Bearer <access_token>
> ```

---

## 📚 Содержание

- [1. Категории](#1-категории)
- [2. Продавцы](#2-продавцы)
- [3. Товары](#3-товары)

---

## 1. Категории

### 1.1. Список всех категорий

**GET** `/categories/`

| Параметр | Тип | Обяз. | Описание               |
| -------- | --- | ----- | ---------------------- |
| —        | —   | —     | Параметры не требуются |

**Пример запроса:**

```http
GET /api/categories/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Accept: application/json
```

**Ответ `200 OK`:**

```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Электроника",
      "slug": "electronics"
    },
    {
      "id": 2,
      "name": "Одежда",
      "slug": "clothing"
    },
    {
      "id": 3,
      "name": "Дом и сад",
      "slug": "home-garden"
    }
  ]
}
```

---

### 1.2. Детали категории

**GET** `/categories/{id}/`

| Параметр | Тип     | Обяз. | Описание     |
| -------- | ------- | ----- | ------------ |
| `id`     | integer | ✅ да | ID категории |

**Пример запроса:**

```http
GET /api/categories/1/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Accept: application/json
```

**Ответ `200 OK`:**

```json
{
  "id": 1,
  "name": "Электроника",
  "slug": "electronics"
}
```

**Ответ `404 Not Found`:**

```json
{
  "detail": "Not found."
}
```

---

## 2. Продавцы

### 2.1. Список всех продавцов

**GET** `/sellers/`

| Параметр | Тип | Обяз. | Описание               |
| -------- | --- | ----- | ---------------------- |
| —        | —   | —     | Параметры не требуются |

**Пример запроса:**

```http
GET /api/sellers/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Accept: application/json
```

**Ответ `200 OK`:**

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Uzum Market Official",
      "rating": 4.8,
      "reviews_count": 1520
    },
    {
      "id": 2,
      "name": "TechStore",
      "rating": 4.5,
      "reviews_count": 340
    }
  ]
}
```

---

### 2.2. Детали продавца

**GET** `/sellers/{id}/`

| Параметр | Тип     | Обяз. | Описание    |
| -------- | ------- | ----- | ----------- |
| `id`     | integer | ✅ да | ID продавца |

**Пример запроса:**

```http
GET /api/sellers/1/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Accept: application/json
```

**Ответ `200 OK`:**

```json
{
  "id": 1,
  "name": "Uzum Market Official",
  "rating": 4.8,
  "reviews_count": 1520
}
```

**Ответ `404 Not Found`:**

```json
{
  "detail": "Not found."
}
```

---

## 3. Товары

### 3.1. Список всех товаров

**GET** `/products/`

| Параметр      | Тип     | Обяз.  | Описание                                    |
| ------------- | ------- | ------ | ------------------------------------------- |
| `page`        | integer | ❌ нет | Номер страницы пагинации (по умолчанию `1`) |
| `page_size`   | integer | ❌ нет | Количество товаров на странице              |
| `category_id` | integer | ❌ нет | Фильтр по ID категории                      |
| `seller_id`   | integer | ❌ нет | Фильтр по ID продавца                       |
| `search`      | string  | ❌ нет | Поиск по названию товара                    |

**Пример запроса:**

```http
GET /api/products/?category_id=1&search=phone&page=1&page_size=10 HTTP/1.1
Host: backend-uzum-market.onrender.com
Accept: application/json
```

**Ответ `200 OK`:**

```json
{
  "count": 42,
  "next": "http://backend-uzum-market.onrender.com/api/products/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "iPhone 15 Pro Max 256GB",
      "description": "Флагманский смартфон Apple с чипом A17 Pro",
      "price": "14999.00",
      "old_price": "17999.00",
      "rating": 4.9,
      "reviews_count": 342,
      "monthly_payment": null,
      "delivery_time": "1-2 дня",
      "image": "https://backend-uzum-market.onrender.com/media/products/iphone15.jpg",
      "images": [
        "https://backend-uzum-market.onrender.com/media/products/iphone15_1.jpg",
        "https://backend-uzum-market.onrender.com/media/products/iphone15_2.jpg"
      ],
      "characteristics": {
        "color": "Титановый",
        "storage": "256 ГБ"
      },
      "is_ad": true,
      "category": {
        "id": 1,
        "name": "Электроника",
        "slug": "electronics"
      },
      "seller": {
        "id": 1,
        "name": "Uzum Market Official",
        "rating": 4.8,
        "reviews_count": 1520
      }
    }
  ]
}
```

---

### 3.2. Детали товара

**GET** `/products/{id}/`

| Параметр | Тип     | Обяз. | Описание  |
| -------- | ------- | ----- | --------- |
| `id`     | integer | ✅ да | ID товара |

**Пример запроса:**

```http
GET /api/products/1/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Accept: application/json
```

**Ответ `200 OK`:**

```json
{
  "id": 1,
  "title": "iPhone 15 Pro Max 256GB",
  "description": "Флагманский смартфон Apple с чипом A17 Pro",
  "price": "14999.00",
  "old_price": "17999.00",
  "rating": 4.9,
  "reviews_count": 342,
  "monthly_payment": null,
  "delivery_time": "1-2 дня",
  "image": "https://backend-uzum-market.onrender.com/media/products/iphone15.jpg",
  "images": [
    "https://backend-uzum-market.onrender.com/media/products/iphone15_1.jpg",
    "https://backend-uzum-market.onrender.com/media/products/iphone15_2.jpg"
  ],
  "characteristics": {
    "color": "Титановый",
    "storage": "256 ГБ"
  },
  "is_ad": true,
  "category": {
    "id": 1,
    "name": "Электроника",
    "slug": "electronics"
  },
  "seller": {
    "id": 1,
    "name": "Uzum Market Official",
    "rating": 4.8,
    "reviews_count": 1520
  }
}
```

**Ответ `404 Not Found`:**

```json
{
  "detail": "Not found."
}
```

---

## 📋 Сводная таблица эндпоинтов

| #   | Метод | Путь                | Авторизация | Описание              |
| --- | ----- | ------------------- | ----------- | --------------------- |
| 1   | GET   | `/categories/`      | Public      | Список всех категорий |
| 2   | GET   | `/categories/{id}/` | Public      | Детали категории      |
| 3   | GET   | `/sellers/`         | Public      | Список всех продавцов |
| 4   | GET   | `/sellers/{id}/`    | Public      | Детали продавца       |
| 5   | GET   | `/products/`        | Public      | Список всех товаров   |
| 6   | GET   | `/products/{id}/`   | Public      | Детали товара         |

---

## 📦 Модели данных

### Category

| Поле   | Тип     | Описание                  |
| ------ | ------- | ------------------------- |
| `id`   | integer | Первичный ключ            |
| `name` | string  | Название категории        |
| `slug` | string  | URL-оптимизированный slug |

### Seller

| Поле            | Тип     | Описание           |
| --------------- | ------- | ------------------ |
| `id`            | integer | Первичный ключ     |
| `name`          | string  | Название продавца  |
| `rating`        | float   | Рейтинг (0.0–5.0)  |
| `reviews_count` | integer | Количество отзывов |

### Product

| Поле              | Тип                     | Описание                          |
| ----------------- | ----------------------- | --------------------------------- |
| `id`              | integer                 | Первичный ключ                    |
| `title`           | string                  | Название товара                   |
| `description`     | string                  | Полное описание                   |
| `price`           | string (decimal)        | Текущая цена                      |
| `old_price`       | string (decimal) · null | Старая цена (скидка)              |
| `rating`          | float                   | Рейтинг товара (0.0–5.0)          |
| `reviews_count`   | integer                 | Количество отзывов                |
| `monthly_payment` | string (decimal) · null | Цена по подписке/рассрочке        |
| `delivery_time`   | string                  | Срок доставки                     |
| `image`           | string (URL)            | Главное изображение               |
| `images`          | array[string]           | Массив дополнительных изображений |
| `characteristics` | object                  | JSON-атрибуты товара              |
| `is_ad`           | boolean                 | Является ли рекламой              |
| `category`        | object                  | Вложенный объект Category         |
| `seller`          | object                  | Вложенный объект Seller           |

---

## 🧩 Swagger / Redoc

Интерактивная документация доступна по адресам:

| Формат             | URL                                                    |
| ------------------ | ------------------------------------------------------ |
| **Swagger UI**     | `https://backend-uzum-market.onrender.com/api/docs/`   |
| **ReDoc**          | `https://backend-uzum-market.onrender.com/api/redoc/`  |
| **OpenAPI Schema** | `https://backend-uzum-market.onrender.com/api/schema/` |

Локально:

| Формат         | URL                                |
| -------------- | ---------------------------------- |
| **Swagger UI** | `http://127.0.0.1:8000/api/docs/`  |
| **ReDoc**      | `http://127.0.0.1:8000/api/redoc/` |

---

## 🔮 Планы развития API

В следующих версиях планируется добавить:

- **Аутентификация** — JWT (djangorestframework-simplejwt)
- **Пользователь** — регистрация, профиль
- **Корзина** — добавление/удаление товаров
- **Заказы** — оформление, статусы
- **Избранное** — добавление товаров в избранное
- **Отзывы** — создание отзывов на товары
- **Write-эндпоинты** — POST/PUT/PATCH для создания и обновления данных (категории, продавцы, товары)

```

```
