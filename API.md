# Uzum Market Clone — API Documentation

> **Статус:** `v1.1.0` · **Формат:** `JSON` · **Кодировка:** `UTF-8`

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

## 🔐 Авторизация (JWT через HttpOnly cookies)

API использует **JWT-токены**, которые хранятся в **защищённых HttpOnly cookies**.
Токены **не возвращаются в теле ответа** и **не доступны через JavaScript** (защита от XSS).

### Как передать cookies

Фронтенд должен отправлять запросы с включёнными credentials:

**Fetch API:**
```js
fetch('https://backend-uzum-market.onrender.com/api/auth/login/', {
  method: 'POST',
  credentials: 'include',  // ← ОБЯЗАТЕЛЬНО
  body: JSON.stringify({ email, password })
})
```

**Axios:**
```js
axios.post('https://backend-uzum-market.onrender.com/api/auth/login/', { email, password }, {
  withCredentials: true  // ← ОБЯЗАТЕЛЬНО
})
```

### Время жизни токенов

| Токен     | Время жизни | Cookie path      |
| --------- | ----------- | ---------------- |
| `access`  | **15 минут** | `/`              |
| `refresh` | **7 дней**   | `/api/auth/`     |

При истечении `access` — вызови `POST /api/auth/refresh/` (без тела, токен берётся из cookie).

> 🔒 Токены передаются в защищённых cookies: `HttpOnly`, `SameSite=Lax`, `Secure` (в production).

---

## 📚 Содержание

- [0. Аутентификация / JWT](#0-аутентификация--jwt)
- [1. Категории](#1-категории)
- [2. Продавцы](#2-продавцы)
- [3. Товары](#3-товары)

---

## 0. Аутентификация / JWT

### 0.1. Регистрация

**POST** `/auth/register/` — создание нового аккаунта.

| Параметр     | Тип    | Обяз.  | Описание                                |
| ------------ | ------ | ------ | --------------------------------------- |
| `email`      | string | ✅ да  | Email (уникальный, регистронезависимый) |
| `password`   | string | ✅ да  | Пароль (мин. сложность)                 |
| `password2`  | string | ✅ да  | Подтверждение пароля                    |
| `first_name` | string | ❌ нет | Имя                                     |
| `last_name`  | string | ❌ нет | Фамилия                                 |
| `phone`      | string | ❌ нет | Телефон                                 |

**Пример запроса:**

```http
POST /api/auth/register/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Content-Type: application/json
Accept: application/json

{
  "email": "user@example.com",
  "password": "StrongPass123!",
  "password2": "StrongPass123!",
  "first_name": "Иван",
  "last_name": "Петров",
  "phone": "+998901234567"
}
```

**Ответ `201 Created`:**

```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "Иван",
  "last_name": "Петров",
  "phone": "+998901234567"
}
```

> ⚠️ **Изменение v1.1:** Токены теперь не возвращаются в ответе. Они выставляются в HttpOnly cookies автоматически.

**Ответ `400 Bad Request`** (email уже занят):

```json
{
  "email": ["Пользователь с таким email уже существует."]
}
```

**Ответ `400 Bad Request`** (пароли не совпадают):

```json
{
  "password2": ["Пароли не совпадают."]
}
```

---

### 0.2. Логин

**POST** `/auth/login/` — вход по email и паролю.

| Параметр   | Тип    | Обяз. | Описание           |
| ---------- | ------ | ----- | ------------------ |
| `email`    | string | ✅ да | Email пользователя |
| `password` | string | ✅ да | Пароль             |

**Пример запроса:**

```http
POST /api/auth/login/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Content-Type: application/json
Accept: application/json
Cookie: (автоматически)

{
  "email": "user@example.com",
  "password": "StrongPass123!"
}
```

**Ответ `200 OK`:**

```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "Иван",
  "last_name": "Петров",
  "phone": "+998901234567"
}
```

> 🔒 Токены `uzum_access_token` и `uzum_refresh_token` устанавливаются в HttpOnly cookies.
> В теле ответа токены **не возвращаются**.

**Ответ `401 Unauthorized`** (неверные данные):

```json
{
  "detail": "No active account found with the given credentials"
}
```

---

### 0.3. Обновление токена

**POST** `/auth/refresh/` — получить новый `access` по `refresh` из cookie.

| Параметр  | Тип    | Обяз. | Описание      |
| --------- | ------ | ----- | ------------- |
| —         | —      | —     | Тело не нужно |

**Пример запроса:**

```http
POST /api/auth/refresh/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Content-Type: application/json
Cookie: uzum_refresh_token=eyJhbGciOiJIUzI1NiIs...
```

**Ответ `200 OK`:**

```
(пустое тело)
```

> 🔒 Новый `access` токен обновляется в cookie `uzum_access_token`.
> Тело ответа пустое — токен передаётся только через cookie.

**Ответ `401 Unauthorized`** (просрочен/невалидный refresh):

```json
{
  "detail": "Token is invalid or expired."
}
```

> ⚠️ При 401 обе cookies удаляются.

---

### 0.4. Выход (Logout)

**POST** `/auth/logout/` — выйти из аккаунта.

| Параметр | Тип | Обяз. | Описание |
| -------- | --- | ----- | -------- |
| —        | —   | —     | Требуется авторизация |

**Пример запроса:**

```http
POST /api/auth/logout/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Cookie: uzum_access_token=..., uzum_refresh_token=...
```

**Ответ `200 OK`:**

```json
{
  "detail": "Successfully logged out."
}
```

> 🗑️ Обе cookies удаляются, refresh-токен добавляется в блэклист.

---

### 0.5. Профиль текущего пользователя

**GET** `/auth/me/` — данные авторизованного пользователя.

| Параметр | Тип | Обяз. | Описание |
| -------- | --- | ----- | -------- |
| —        | —   | —     | Требуется авторизация (cookie) |

**Пример запроса:**

```http
GET /api/auth/me/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Cookie: uzum_access_token=eyJhbGciOiJIUzI1NiIs...
```

**Ответ `200 OK`:**

```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "Иван",
  "last_name": "Петров",
  "phone": "+998901234567"
}
```

**Ответ `401 Unauthorized`** (без cookie):

```json
{
  "detail": "Authentication credentials were not provided."
}
```

---

## 1. Категории

### 1.1. Список всех категорий

**GET** `/categories/`

| Параметр | Тип | Обяз. | Описание |
| -------- | --- | ----- | -------- |
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

| Параметр | Тип | Обяз. | Описание |
| -------- | --- | ----- | -------- |
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

| Параметр    | Тип     | Обяз.  | Описание                                                                         |
| ----------- | ------- | ------ | -------------------------------------------------------------------------------- |
| `page`      | integer | ❌ нет | Номер страницы пагинации (по умолчанию `1`)                                      |
| `page_size` | integer | ❌ нет | Количество товаров на странице (по умолчанию `10`)                               |
| `category`  | integer | ❌ нет | Фильтр по ID категории                                                           |
| `seller`    | integer | ❌ нет | Фильтр по ID продавца                                                            |
| `search`    | string  | ❌ нет | Поиск по названию и описанию товара                                              |
| `ordering`  | string  | ❌ нет | Сортировка: `price`, `rating`, `created_at` (с `-` для убывания, напр. `-price`) |

**Пример запроса:**

```http
GET /api/products/?category=1&search=phone&ordering=-price&page=1 HTTP/1.1
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

| #   | Метод | Путь                | Авторизация | Описание                      |
| --- | ----- | ------------------- | ----------- | ----------------------------- |
| 1   | POST  | `/auth/register/`   | Public      | Регистрация пользователя      |
| 2   | POST  | `/auth/login/`      | Public      | Логин (cookie-автоматически)  |
| 3   | POST  | `/auth/refresh/`    | Public      | Обновить access (из cookie)   |
| 4   | POST  | `/auth/logout/`     | Auth        | Выход (удалить cookies)       |
| 5   | GET   | `/auth/me/`         | Auth        | Профиль текущего пользователя |
| 6   | GET   | `/categories/`      | Public      | Список всех категорий         |
| 7   | GET   | `/categories/{id}/` | Public      | Детали категории              |
| 8   | GET   | `/sellers/`         | Public      | Список всех продавцов         |
| 9   | GET   | `/sellers/{id}/`    | Public      | Детали продавца               |
| 10  | GET   | `/products/`        | Public      | Список всех товаров           |
| 11  | GET   | `/products/{id}/`   | Public      | Детали товара                 |

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
| **Swagger UI**     | `https://backend-uzum-market.onrender.com/api/schema/swagger-ui/`   |
| **OpenAPI Schema** | `https://backend-uzum-market.onrender.com/api/schema/` |

Локально:

| Формат         | URL                                |
| -------------- | ---------------------------------- |
| **Swagger UI** | `http://127.0.0.1:8000/api/schema/swagger-ui/`  |

---

## 🔮 Планы развития API

В следующих версиях планируется добавить:

- **Корзина** — добавление/удаление товаров
- **Заказы** — оформление, статусы
- **Избранное** — добавление товаров в избранное
- **Отзывы** — создание отзывов на товары
- **Write-эндпоинты** — POST/PUT/PATCH для создания и обновления данных (категории, продавцы, товары)
