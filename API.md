# Uzum Market Clone — API Documentation

> **Статус:** `v1.2.0` · **Формат:** `JSON` · **Кодировка:** `UTF-8`
>
> Документация соответствует коду: каждые запрос/ответ здесь покрыты тестами
> (`python manage.py test --settings=config.test_settings`), а OpenAPI-схема генерируется
> из тех же сериализаторов и проверяется в CI (`--fail-on-warn`).

---

## 📌 Base URL

| Окружение      | URL                                            |
| -------------- | ---------------------------------------------- |
| **Production** | `https://backend-uzum-market.onrender.com/api` |
| **Local**      | `http://127.0.0.1:8000/api`                    |

| Header         | Значение           |
| -------------- | ------------------ |
| `Content-Type` | `application/json` |
| `Accept`       | `application/json` |

Все списки отдаются с `Content-Encoding: gzip`, если клиент прислал `Accept-Encoding: gzip`
(экономия ~90% на каталоге), и с `ETag` — можно слать `If-None-Match` и получать `304`.

---

## 🔐 Авторизация: JWT в HttpOnly cookies

Токены **не возвращаются в теле ответа** и не доступны JavaScript (защита от XSS).
Доступны два способа передать access-токен — на выбор клиента:

| Способ                          | Кто использует      | Как                |
| ------------------------------- | ------------------- | ------------------ |
| Cookie `uzum_access_token`      | браузер (SPA)      | автоматически      |
| `Authorization: Bearer <token>` | мобильные/серверные | выдать из login    |

Токен, выданный `POST /auth/login/`, живёт **15 минут** (`ACCESS_TOKEN_MINUTES`),
refresh — **7 дней** (`REFRESH_TOKEN_DAYS`).

| Cookie               | Path         | Флаги                              |
| -------------------- | ------------ | ---------------------------------- |
| `uzum_access_token`  | `/`          | `HttpOnly`, `Secure`, `SameSite`   |
| `uzum_refresh_token` | `/api/auth/` | `HttpOnly`, `Secure`, `SameSite`   |
| `uzum_csrf`          | `/`          | **не** HttpOnly (читается из JS)   |

### Два режима деплоя — выберите один

**Режим A — same-site (рекомендуется).** Фронт проксирует `/api` на бэкенд, для браузера всё
в одном origin. Тогда достаточно `COOKIE_SAMESITE=Lax`, и ничего дополнительно не нужно:

```js
// next.config.js
async rewrites() {
  return [{ source: '/api/:path*', destination: 'https://backend-uzum-market.onrender.com/api/:path*' }]
}
```

**Режим B — кросс-доменный (by default в проде).** `COOKIE_SAMESITE=None` (+ обязателен `Secure`,
то есть HTTPS). В этом режиме **все** unsafe-запросы (POST/PUT/PATCH/DELETE) обязаны нести
заголовок `X-CSRFToken` с значением cookie `uzum_csrf` — иначе `403`. Это double-submit-защита:
DRF не проверяет CSRF для cookie-авторизации, а `SameSite=None` отправляет cookie на любой сайт.

**Fetch API (режим B):**

```js
// 1. один раз на сессию — получить CSRF-токен (и сами cookies)
await fetch(`${API}/auth/csrf/`, { credentials: 'include' })
const csrf = document.cookie.match(/(?:^|;\s*)uzum_csrf=([^;]*)/)?.[1]

// 2. логин
await fetch(`${API}/auth/login/`, {
  method: 'POST',
  credentials: 'include',            // ← ОБЯЗАТЕЛЬНО
  headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
  body: JSON.stringify({ email, password }),
})

// 3. любой GET с авторизацией — заголовок не нужен
await fetch(`${API}/auth/me/`, { credentials: 'include' })
```

**Axios:**

```js
const http = axios.create({ baseURL: API, withCredentials: true })
http.interceptors.request.use((cfg) => {
  if (!['get', 'head', 'options'].includes(cfg.method)) cfg.headers['X-CSRFToken'] = readCookie('uzum_csrf')
  return cfg
})
```

**Обновление токена:** при `401` от любого эндпоинта — `POST /auth/refresh/` (без тела)
и повтор исходного запроса; если и он вернул `401` — на страницу логина (cookies уже стёрты).

### Время жизни и отзыв

| Событие               | Что происходит                                                              |
| --------------------- | -------------------------------------------------------------------------- |
| `POST /auth/refresh/` | новый `access`; **refresh ротируется** (ROTATE_REFRESH_TOKENS), старый уходит в блэклист |
| `POST /auth/logout/`  | refresh добавляется в блэклист, обе cookies удаляются                      |
| `401` на protected    | access истёк/невалиден; публичные эндпоинты при этом работают как аноним   |

> ⚠️ Изменения относительно `v1.1`: отзыв refresh-токена реально работает (был тихий баг),
> `DELETE`-подобных публичных write-эндпоинтов по-прежнему нет.

---

## 📚 Содержание

- [🔐 Авторизация: JWT в HttpOnly cookies](#-авторизация-jwt-в-httponly-cookies)
- [0. Аутентификация / JWT](#0-аутентификация--jwt)
- [1. Категории](#1-категории)
- [2. Продавцы](#2-продавцы)
- [3. Товары](#3-товары)
- [4. Ошибки и лимиты](#4-ошибки-и-лимиты)
- [5. Форматы списков (пагинация)](#5-форматы-списков-пагинация)
- [📋 Сводная таблица эндпоинтов](#-сводная-таблица-эндпоинтов)
- [📦 Модели данных](#-модели-данных)
- [🧩 Swagger / Redoc](#-swagger--redoc)
- [🛠 Конфигурация (переменные окружения)](#-конфигурация-переменные-окружения)
- [🚀 Локальный запуск и проверки](#-локальный-запуск-и-проверки)
- [🔮 Планы развития API](#-планы-развития-api)

---

## 0. Аутентификация / JWT

### 0.1. Регистрация

**POST** `/auth/register/` — создание аккаунта. Пользователь **сразу авторизован**
(set-cookie в этом же ответе), токены в теле не возвращаются.

| Параметр     | Тип    | Обяз. | Описание                                       |
| ------------ | ------ | ----- | ---------------------------------------------- |
| `email`      | string | ✅ да | Нормализуется к `strip().lower()`, уникален    |
| `password`  | string | ✅ да | ≥ 8 симв., не только цифры, не похож на email  |
| `password2`  | string | ✅ да | Подтверждение пароля                           |
| `first_name` | string | ❌ нет | Имя                                            |
| `last_name`  | string | ❌ нет | Фамилия                                        |
| `phone`      | string | ❌ нет | `+998901234567` (цифры, пробелы, `()`, `-`, `+`) |

```http
POST /api/auth/register/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Content-Type: application/json
Accept: application/json
X-CSRFToken: 4tZ6Wb6bYNJw_f1bcnaylExulOKsMsSIuOtOH2i9LFg   # только в режиме B

{
  "email": "user@example.com",
  "password": "Str0ng-Pass-99",
  "password2": "Str0ng-Pass-99",
  "first_name": "Иван",
  "last_name": "Петров",
  "phone": "+998901234567"
}
```

**Ответ `201 Created`** (+ `Set-Cookie` с access/refresh):

```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "Иван",
  "last_name": "Петров",
  "phone": "+998901234567",
  "date_joined": "2026-08-28T17:02:13.977747Z"
}
```

**Ответ `400 Bad Request`:**

```json
{ "email": ["Пользователь с таким email уже существует."] }
```

```json
{ "password": ["Этот пароль слишком похож на другую информацию о пользователе."] }
```

Лимит: `THROTTLE_REGISTER` (по умолчанию **5/час** на IP) → `429`.

---

### 0.2. Логин

**POST** `/auth/login/` — вход по email и паролю; ставит обе cookies.

| Параметр  | Тип    | Обяз. | Описание                     |
| --------- | ------ | ----- | ---------------------------- |
| `email`   | string | ✅ да | Регистр не важен             |
| `password`| string | ✅ да | Пароль                       |

```http
POST /api/auth/login/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Content-Type: application/json
Cookie: (автоматически)

{ "email": "user@example.com", "password": "Str0ng-Pass-99" }
```

**Ответ `200 OK`** — тело то же, что у `/me/`; токены **только в cookies**.

**Ответ `401 Unauthorized`:**

```json
{ "detail": "No active account found with the given credentials" }
```

Лимит: `THROTTLE_LOGIN` (по умолчанию **10/мин** на IP) → `429`:

```json
{ "detail": "Ещё слишком много запросов. Повторите через N секунд." }
```

---

### 0.3. Обновление токена

**POST** `/auth/refresh/` — новый `access` (+ ротация `refresh`) из cookie.

| Параметр  | Тип    | Обяз. | Описание                                        |
| --------- | ------ | ----- | ----------------------------------------------- |
| `refresh` | string | ❌    | свой refresh-токен; по умолчанию берётся из cookie |

Тело не нужно: `POST` без тела, с пустым телом, с `application/x-www-form-urlencoded` или с
JSON — всё даёт `204` (раньше form-encoded падал с `500` из-за мутации неизменяемого `QueryDict`).

> Если `refresh` передан в теле, используется **он**, а не cookie: битый/отозванный токен в теле
> вернёт `401` (и очистит cookies), а не «тихий успех» за счёт валидной cookie. Это нужно
> мобильным/серверным клиентам, которые хранят refresh сами.

```http
POST /api/auth/refresh/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Cookie: uzum_refresh_token=eyJhbGciOiJIUzI1NiIs…
```

**Ответ `204 No Content`** — тело пустое, новый `access` (и, при ротации, новый `refresh`)
в `Set-Cookie`.

**Ответ `401 Unauthorized`** (просрочен/отозван/нет cookie) — **обе cookies удаляются**:

```json
{ "detail": "Token is invalid or expired." }
```

---

### 0.4. Выход (Logout)

**POST** `/auth/logout/` — отзывает refresh-токен (блэклист) и стирает cookies.
Доступен и без валидного access (иначе пользователь с истёкшим токеном не смог бы разлогиниться).

```http
POST /api/auth/logout/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Cookie: uzum_access_token=…, uzum_refresh_token=…
```

**Ответ `200 OK`:**

```json
{ "detail": "Successfully logged out." }
```

---

### 0.5. CSRF-токен (только для режима B)

**GET** `/auth/csrf/` — выдаёт cookie `uzum_csrf` для заголовка `X-CSRFToken`.
Нужен один раз на сессию, до первого unsafe-запроса.

**Ответ `200 OK`:** `{ "detail": "ok" }`

---

### 0.6. Профиль текущего пользователя

**GET** `/auth/me/` — требует авторизации (cookie **или** `Authorization: Bearer`).

```http
GET /api/auth/me/ HTTP/1.1
Host: backend-uzum-market.onrender.com
Cookie: uzum_access_token=eyJhbGciOiJIUzI1NiIs…
```

**Ответ `200 OK`:**

```json
{
  "id": 1,
  "email": "user@example.com",
  "first_name": "Иван",
  "last_name": "Петров",
  "phone": "+998901234567",
  "date_joined": "2026-08-28T17:02:13.977747Z"
}
```

**Ответ `401 Unauthorized`:** `{ "detail": "Authentication credentials were not provided." }`

---

## 1. Категории

### 1.1. Список всех категорий

**GET** `/categories/` — параметры не требуются; ответ кэшируется на
`CATALOG_CACHE_SECONDS` (60 с) и инвалидируется при любом изменении каталога.

```http
GET /api/categories/ HTTP/1.1
Accept: application/json
```

**Ответ `200 OK`:**

```json
{
  "count": 5,
  "page_size": 10,
  "total_pages": 1,
  "next": null,
  "previous": null,
  "results": [
    { "id": 1, "name": "Электроника", "slug": "electronics" },
    { "id": 2, "name": "Одежда", "slug": "clothing" }
  ]
}
```

### 1.2. Детали категории

**GET** `/categories/{id}/` → `{ "id": 1, "name": "Электроника", "slug": "electronics" }`
или `404 { "detail": "Not found." }`.

---

## 2. Продавцы

### 2.1. Список всех продавцов

**GET** `/sellers/` · сортировка: `?ordering=rating|reviews_count|name` (можно с `-`),
поиск: `?search=<подстрока названия>`.

```json
{
  "count": 4,
  "page_size": 10,
  "total_pages": 1,
  "next": null,
  "previous": null,
  "results": [
    { "id": 1, "name": "Uzum Market Official", "rating": "4.80", "reviews_count": 1520 },
    { "id": 2, "name": "TechStore", "rating": "4.50", "reviews_count": 340 }
  ]
}
```

> `rating` — **строка** с ровно двумя знаками после запятой (`DecimalField(3,2)`):
> float давал `4.7999999…` в JSON. Приводите к числу на клиенте, если нужно.

### 2.2. Детали продавца

**GET** `/sellers/{id}/` — тот же объект, что и в списке.

---

## 3. Товары

### 3.1. Список товаров

**GET** `/products/`

| Параметр        | Тип             | Обяз. | Описание                                                              |
| --------------- | --------------- | ----- | --------------------------------------------------------------------- |
| `page`          | integer         | ❌     | Номер страницы (по умолчанию `1`)                                     |
| `page_size`     | integer         | ❌     | Размер страницы, по умолчанию `10`, максимум `PAGE_SIZE_MAX` (`100`) |
| `category`      | integer         | ❌     | Фильтр по ID категории                                                 |
| `category_slug` | string          | ❌     | Фильтр по slug (`electronics`)                                         |
| `seller`        | integer         | ❌     | Фильтр по ID продавца                                                  |
| `min_price`     | number          | ❌     | Цена от (включительно)                                                 |
| `max_price`     | number          | ❌     | Цена до (включительно)                                                 |
| `min_rating`    | number          | ❌     | Рейтинг от                                                             |
| `is_ad`         | boolean         | ❌     | `true` — только рекламные, `false` — только обычные                   |
| `discounted`    | boolean         | ❌     | `true` — только те, у кого `old_price > price`                         |
| `search`        | string          | ❌     | Подстрока в `title` **или** `description` (без учёта регистра)         |
| `ordering`      | string          | ❌     | `price`, `rating`, `reviews_count`, `created_at`, `old_price`, `id`; `-` для убывания |

Неизвестный параметр → `400` (а не «200, но фильтр проигнорирован»):

```json
{ "query": ["Неизвестные параметры: pages. Разрешённые: category, discounted, …"] }
```

```http
GET /api/products/?category=1&min_price=1000000&ordering=-price&page=1&page_size=20 HTTP/1.1
Accept: application/json
```

**Ответ `200 OK`** — элементы **укрупнённой сетки** (без `description`, `characteristics`,
`images`, `seller`, чтобы гонять меньше байт):

```json
{
  "count": 42,
  "page_size": 20,
  "total_pages": 3,
  "next": "http://backend-uzum-market.onrender.com/api/products/?page=2&page_size=20",
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Беспроводные наушники Apple AirPods Pro 2, MagSafe Type-C",
      "price": "3190000.00",
      "old_price": "3600000.00",
      "discount_percent": 11,
      "rating": "4.95",
      "reviews_count": 450,
      "monthly_payment": "265833.00",
      "delivery_time": "1 день",
      "image": "https://cdn.example.com/media/products/airpods.jpg",
      "is_ad": true,
      "category": { "id": 1, "name": "Электроника", "slug": "electronics" },
      "created_at": "2026-08-22T13:51:00Z"
    }
  ]
}
```

### 3.2. Детали товара

**GET** `/products/{id}/` — полная карточка:

```json
{
  "id": 1,
  "title": "Беспроводные наушники Apple AirPods Pro 2, MagSafe Type-C",
  "description": "Наушники AirPods Pro 2 с активным шумоподавлением…",
  "price": "3190000.00",
  "old_price": "3600000.00",
  "discount_percent": 11,
  "rating": "4.95",
  "reviews_count": 450,
  "monthly_payment": "265833.00",
  "delivery_time": "1 день",
  "image": "https://cdn.example.com/media/products/airpods.jpg",
  "images": [
    "https://cdn.example.com/media/products/airpods_1.jpg",
    "https://cdn.example.com/media/products/airpods_2.jpg"
  ],
  "characteristics": {
    "Время работы": "До 6 часов",
    "Разъём зарядки": "USB Type-C",
    "Шумоподавление": "Активное (ANC)"
  },
  "is_ad": true,
  "category": { "id": 1, "name": "Электроника", "slug": "electronics" },
  "seller": { "id": 2, "name": "TechStore", "rating": "4.50", "reviews_count": 340 },
  "created_at": "2026-08-22T13:51:00Z",
  "updated_at": "2026-08-28T09:14:02Z"
}
```

**`image` / `images[]` — абсолютные URL.** Значение, которое лежит в БД как `https://…`,
отдаётся как есть; относительный путь (`products/x.jpg`) разворачивается в
`{MEDIA_URL}` текущего запроса. Раньше `image` был `ImageField`, и любая внешняя ссылка
превращалась в битый `/media/https%3A/…`.

---

## 4. Ошибки и лимиты

| Код | Когда                                                       | Тело                                              |
| --- | ----------------------------------------------------------- | -------------------------------------------------- |
| 400 | ошибка валидации / неизвестный query-параметр               | `{"email": ["…"]}` или `{"query": ["…"]}`          |
| 401 | нет авторизации, истёк/отозван refresh, неверные данные     | `{"detail": "…"}`                                  |
| 403 | не пройден CSRF-заголовок (режим B) или прав не хватает     | `{"detail": "CSRF-проверка не пройдена: …"}`        |
| 404 | объект или страница пагинации не найдены                    | `{"detail": "Not found."}`                         |
| 409 | гонка на уникальности (две параллельные регистрации)         | `{"detail": "Такие данные уже существуют…"}`        |
| 429 | троттлинг `login` / `register` / `refresh`                  | `{"detail": "Ещё слишком много запросов. …"}`       |
| 503 | база временно недоступна                                    | `{"detail": "Временная проблема с базой данных…"}`  |

Все ошибки — JSON (HTML-трейсбек только при `DEBUG=True`).

---

## 5. Форматы списков (пагинация)

```json
{
  "count": 42,          // всего строк по фильтру
  "page_size": 20,      // фактически применённый размер (учтён потолок)
  "total_pages": 3,
  "next": "…/api/products/?page=2&page_size=20",   // null на последней странице
  "previous": null,
  "results": [ … ]
}
```

`page` вне диапазона → `404`, `page` не число → `400`.

---

## 📋 Сводная таблица эндпоинтов

| #   | Метод | Путь                | Авторизация       | Описание                                  |
| --- | ----- | ------------------- | ----------------- | ----------------------------------------- |
| 1   | POST  | `/auth/register/`   | Public            | Регистрация + сразу выданные cookies      |
| 2   | POST  | `/auth/login/`      | Public            | Логин (cookies)                           |
| 3   | POST  | `/auth/refresh/`    | Public (cookie)   | Новый access, ротация refresh             |
| 4   | POST  | `/auth/logout/`     | Public            | Отзыв refresh + чистка cookies            |
| 5   | GET   | `/auth/csrf/`       | Public            | CSRF-токен для unsafe-запросов            |
| 6   | GET   | `/auth/me/`         | Auth              | Профиль текущего пользователя             |
| 7   | GET   | `/categories/`      | Public            | Категории (кэш 60 с)                       |
| 8   | GET   | `/categories/{id}/` | Public            | Одна категория                            |
| 9   | GET   | `/sellers/`         | Public            | Продавцы (сортировка/поиск)                |
| 10  | GET   | `/sellers/{id}/`    | Public            | Один продавец                             |
| 11  | GET   | `/products/`        | Public / Auth     | Каталог: фильтры, поиск, сортировка        |
| 12  | GET   | `/products/{id}/`   | Public / Auth     | Полная карточка товара                    |

Публичные эндпоинты работают и с битой/просроченной cookie — сервер считает такой запрос
анонимным, а не ошибкой.

---

## 📦 Модели данных

### Category

| Поле   | Тип     | Описание                  |
| ------ | ------- | ------------------------- |
| `id`   | integer | Первичный ключ            |
| `name` | string  | Название категории        |
| `slug` | string  | URL-оптимизированный slug (уникален) |

### Seller

| Поле            | Тип            | Описание              |
| --------------- | -------------- | --------------------- |
| `id`            | integer        | Первичный ключ        |
| `name`          | string         | Название продавца      |
| `rating`        | string (0.00–5.00) | Средняя оценка     |
| `reviews_count` | integer        | Количество отзывов     |

### Product

| Поле               | Тип                     | Описание                                     |
| ------------------ | ----------------------- | -------------------------------------------- |
| `id`               | integer                 | PK                                            |
| `title`            | string                  | Название                                      |
| `description`      | string                  | Полное описание (только в деталях)            |
| `price`            | string (decimal)        | Текущая цена                                  |
| `old_price`        | string (decimal) · null | Цена до скидки                                |
| `discount_percent` | integer                 | Посчитано на бэке, `0` если скидки нет        |
| `rating`           | string (decimal)        | 0.00–5.00                                     |
| `reviews_count`    | integer                 | Число отзывов                                 |
| `monthly_payment`  | string (decimal) · null | Платёж в рассрочку                             |
| `delivery_time`    | string                  | Срок доставки                                  |
| `image`            | string (URL) · null     | Главное изображение                           |
| `images`           | array[string]           | Дополнительные изображения                    |
| `characteristics`  | object<string,string>   | Характеристики                                 |
| `is_ad`            | boolean                 | Рекламная выдача                               |
| `category`         | object                  | Вложенная Category                             |
| `seller`           | object                  | Вложенный Seller (только в деталях)            |
| `created_at`       | string (date-time, UTC) | Когда добавлен                                 |
| `updated_at`       | string (date-time, UTC) | Последнее изменение                            |

---

## 🧩 Swagger / Redoc

| Формат             | URL                                                             |
| ------------------ | --------------------------------------------------------------- |
| **OpenAPI Schema** | `/api/schema/`                                                   |
| **Swagger UI**     | `/api/schema/swagger-ui/`  (и старый алиас `/api/docs/`)         |
| **Redoc**          | `/api/schema/redoc/`                                             |

`Try it out` работает и для cookie-запросов (браузер подставит cookie), и для
`Authorization: Bearer` (схема `jwtAuth`).

---

## 🛠 Конфигурация (переменные окружения)

Все значения читаются из окружения / `.env` в `config/settings.py`. Ключей `SECRET_KEY` и
`DATABASE_URL` достаточно для запуска; остальное — опционально.

### Обязательное на проде

| Переменная | Дефолт | Значение |
|---|---|---|
| `SECRET_KEY` | debug-заглушка (только при `DEBUG=True`) | генерировать: `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"` |
| `DEBUG` | `True` | на проде `False` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | через запятую; `*` допустим только при `DEBUG=True` |
| `DATABASE_URL` | при `DEBUG=True` → `sqlite:///db.sqlite3`; при `DEBUG=False` приложение падает на старте | строка подключения. **На Render это Internal Database URL** (не External!) |

### Домены, cookies, TLS

| Переменная | Дефолт | Значение |
|---|---|---|
| `CSRF_TRUSTED_ORIGINS` | — | через запятую, с протоколом: `https://uzum.uzummarket.uz` — без этого `403` на unsafe-запросах за прокси |
| `USE_X_FORWARDED_HOST` | `False` | доверять `Host` с прокси |
| `TRUST_PROXY_TLS_HEADER` | `True` | включает `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')`; снять галку, если TLS не терминируется прокси (иначе вместо `403` будет 301-цикл) |
| `SECURE_SSL_REDIRECT` | `= not DEBUG` | редирект http → https |
| `SECURE_HSTS_SECONDS` | `31536000` | при `DEBUG=False` |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` / `SECURE_HSTS_PRELOAD` | `False` | включать только на своём домене (для `*.onrender.com` — нельзя) |
| `COOKIE_SECURE` | `= not DEBUG` | флаг `Secure` у auth-куки и `SameSite=None` |
| `COOKIE_SAMESITE` | `Lax` | `Lax` (тот же origin/прокси) или `None` (кросс-домен, требует `COOKIE_SECURE=True`) |
| `CSRF_COOKIE_NAME` | `uzum_csrf` | имя double-submit-cookies; **не** переиспользуйте `csrftoken` |
| `COOKIE_DOMAIN` | — | только если cookies нужны на поддоменах (`.example.com`) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | через запятую, без завершающего `/`; на проде обязателен адрес фронтенда |

### JWT

| Переменная | Дефолт | Значение |
|---|---|---|
| `ACCESS_TOKEN_MINUTES` | `15` | TTL access-токена (он же `Max-Age` cookie — разъехаться не могут, `cookies.py` читает `SIMPLE_JWT`) |
| `REFRESH_TOKEN_DAYS` | `7` | TTL refresh-токена |
| `JWT_ROTATE_REFRESH` | `True` | ротация refresh |
| `JWT_BLACKLIST_AFTER_ROTATION` | `True` | старый refresh отзывается (нужен пакет `token_blacklist`) |
| `ACCESS_COOKIE_NAME` / `REFRESH_COOKIE_NAME` | `uzum_access_token` / `uzum_refresh_token` | имена HttpOnly-cookie |
| `ACCESS_COOKIE_PATH` / `REFRESH_COOKIE_PATH` | `/` / `/api/auth/` | `Path` cookie (refresh не светится на всём домене) |
| `COOKIE_HTTP_ONLY` | `True` | отключать не нужно ни в одном из режимов |

### Медиа и статики

| Переменная | Дефолт | Значение |
|---|---|---|
| `MEDIA_URL` | `/media/` | путь, по которому отдаются файлы (или базовый URL бакета) |
| `SERVE_MEDIA` | `= DEBUG` | раздать `MEDIA_ROOT` из приложения. На проде — только если `MEDIA_ROOT` переживает деплой |
| `USE_S3` | `False` | хранить загрузки в S3/R2 (нужен `requirements/storage.txt` + `django-storages`) |
| `STATIC_MANIFEST_REQUIRED` | `False` | форсирует Manifest-хранилище WhiteNoise (хэши + `immutable`) даже когда `staticfiles/staticfiles.json` ещё нет — ставит `build.sh` перед `collectstatic` |
| `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_QUERYSTRING_AUTH` | — | настройки хранилища; `AWS_S3_CUSTOM_DOMAIN` — для CDN |
| `AWS_SECRET_ACCESS_KEY` / `AWS_ACCESS_KEY_ID` | — | ключи (в `.env`, не в репозитории) |

### Кэш, лимиты, поиск

| Переменная | Дефолт | Значение |
|---|---|---|
| `REDIS_URL` | — | без неё — LocMem: **троттлинг и кэш свои на каждого воркера**, поэтому лимиты делённые на 3 воркера (`THROTTLE_*`) нужно учитывать при включении Redis |
| `PAGE_SIZE` / `PAGE_SIZE_MAX` | `10` / `100` | размер страницы каталога по умолчанию и потолок `page_size` |
| `CATALOG_CACHE_SECONDS` | `60` | TTL кэша списков (инвалидируется при записи) |
| `THROTTLE_LOGIN` | `10/min` | лимит на `POST /auth/login/` с одного IP (`X-Forwarded-For`) |
| `THROTTLE_REGISTER` | `5/hour` | лимит на `POST /auth/register/` |
| `THROTTLE_REFRESH` | `60/hour` | лимит на `POST /auth/refresh/` |
| `SEARCH_*` | — | поиска с опечатками/`pg_trgm` нет: `search` = `icontains` по `title` + `description` (см. follow-up в `AUDIT.md`) |

### Прочее

| Переменная | Дефолт | Значение |
|---|---|---|
| `FRONTEND_URL` | `http://localhost:3000` | участвует в `CSRF_TRUSTED_ORIGINS`/CORS-документации |
| `EMAIL_BACKEND` | `console` при `DEBUG=True`, `smtp` иначе | почта в консоли локально, SMTP на проде |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_USE_TLS` / `EMAIL_TIMEOUT` | `smtp.gmail.com`/`587`/—/—/`True`/`10` | SMTP-подключение; `EMAIL_HOST_USER` заодно подставляется в `DEFAULT_FROM_EMAIL` |
| `DEFAULT_FROM_EMAIL` | `uzum@localhost` | — |
| `DJANGO_SETTINGS_MODULE` | `config.settings` | в тестах — `config.test_settings` |

> **Не читается:** `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (исторические ключи —
> всё описание БД живёт в `DATABASE_URL`), `MAILERS`, а также ключи `SIMPLE_JWT["AUTH_COOKIE_*"]`
> (их формат устарел — параметры cookie собраны в `settings.JWT_COOKIE`).

---
## 🚀 Локальный запуск и проверки

```bash
cp .env.example .env                 # достаточно SECRET_KEY (>= 50 символов)
pip install -r requirements/requirements.txt

python manage.py migrate             # без DATABASE_URL в DEBUG поднимется локальный db.sqlite3
python manage.py seed --force        # демо-данные (по умолчанию seed ничего не трогает)
python manage.py createsuperuser     # админка: /admin/
python manage.py runserver
```

Для Postgres вместо sqlite: `createdb uzum_db` либо `export DATABASE_URL=postgres://…`.
Тесты ничего внешнего не требуют:
`python manage.py test --settings=config.test_settings` (sqlite `:memory:`, свой SECRET_KEY
и лимиты заданы в самих `config/test_settings.py`).

Проверки, которые прогоняет CI (файл `ci.yml` лежит в корне репозитория; включить —
`git mv ci.yml .github/workflows/ci.yml`):

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py spectacular --file /tmp/schema.yml --validate --fail-on-warn
python manage.py test --settings=config.test_settings
ruff check . && ruff format --check .
```

Полезные флаги `seed`: `--force` (перезалить демо), `--reset` (сначала очистить),
`--fix-encoding` (разовая починка «битой» кириллицы; раньше делалась на каждый деплой).

---

## 🔮 Планы развития API

- **Корзина / Избранное / Заказы / Отзывы** — текущий минимум: `POST /cart/items/`,
  `GET /orders/` и т.д. (см. `AUDIT.md`, раздел E-4, по модели `ProductImage`).
- **Write-эндпоинты каталога** — `POST/PUT/PATCH` для продавца: понадобится
  ownership-проверка (`seller == request.user.seller`) и нормальная CSRF-схема.
- **Поиск** — `pg_trgm` + GIN-индекс вместо `LIKE '%…%'` (сейчас `icontains` = полный скан).
- **Password reset** — настройки почты уже рабочие (`EMAIL_*`), нужен сам флоу.
