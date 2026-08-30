# Uzum Market Clone — API Documentation

> **Статус:** `v2.0.0` (cookie-session) · **Формат:** `JSON` · **Кодировка:** `UTF-8`
>
> Документация соответствует коду: каждый запрос/ответ здесь покрыт тестами
> (`python manage.py test --settings=config.test_settings` — 99 тестов), а OpenAPI-схема
> генерируется из тех же сериализаторов и валидируется без ошибок
> (`python manage.py spectacular --file schema.yml --validate`).
>
> Интерактивная схема: `/api/docs/` (Swagger), `/api/schema/redoc/`, `/api/schema/`.

---

## 📌 Base URL

| Окружение      | URL                          |
| -------------- | ---------------------------- |
| **Production** | `https://<ваш-домен>/api`    |
| **Local**      | `http://127.0.0.1:8000/api`  |

Общие правила (§4 ТЗ):

- Все маршруты под `/api/`, без версионирования.
- Деньги — **целые числа** (сумы). Рейтинги — числа с одним знаком.
- Даты — ISO-8601 UTC с суффиксом `Z`: `"2026-08-30T12:00:00.000000Z"`.
- Идентификаторы — целые числа; в GET товара/продавца `id` и `slug` взаимозаменяемы.
- Тело запроса — JSON ≤ 256 КБ (кроме `POST /uploads/` — multipart).

### Конверт списков

```json
{
  "count": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3,
  "next": true,
  "previous": false,
  "results": []
}
```

`next`/`previous` — **булевы** (не URL). Непагинируемые списки (`categories`, `sellers`,
`products/mine`, `orders`, `shop/orders`) отдают тот же конверт с `total_pages: 1`.

### Формат ошибок

```json
{ "detail": "Проверьте правильность полей.", "fields": { "email": "Введите корректный email." } }
```

Коды: `400` (валидация/бизнес-правило), `401` (нет сессии), `403` (не ваш объект/CSRF),
`404` (не найдено или чужое), `409` (конфликт). `DELETE` → `200 {"detail": "..."}`.

---

## 🔐 Авторизация: сессия в cookie + CSRF

Токены в теле ответа **не возвращаются**. Авторизация — Django-сессия в HttpOnly-cookie:

| Cookie            | Флаги                                       | Назначение                     |
| ----------------- | ------------------------------------------- | ------------------------------ |
| `uzum_sessionid`  | `HttpOnly; Path=/; SameSite=Lax; Secure`(prod), 7 дней | сессия пользователя |
| `uzum_csrf`       | читается JavaScript, `SameSite=Lax`         | double-submit CSRF             |

Каждый небезопасный метод (`POST/PATCH/PUT/DELETE`) требует заголовок
`X-CSRFToken: <значение куки uzum_csrf>`. Исключение — `PUT /orders/` (превью корзины):
он доступен без авторизации и без CSRF. Токен выдаёт `GET /auth/csrf/`
(заодно ставит куку `uzum_csrf`).

### Эндпоинты

| Метод  | Путь            | Доступ | Описание |
| ------ | --------------- | ------ | -------- |
| GET    | `/auth/csrf/`   | все    | Выдать куку+токен CSRF: `{"detail":"CSRF-токен выдан","csrfToken":"..."}` |
| POST   | `/auth/register/` | анон  | `{email, password, password2, first_name, last_name?, phone?, shop_name?}` → 201 профиль + вход; магазин создаётся сразу (§0.1 ТЗ): `shop_name` или «Имя — магазин» |
| POST   | `/auth/login/`  | анон   | `{email, password}` → 200 профиль, ставит обе куки |
| POST   | `/auth/logout/` | все    | Гасит сессию, чистит обе куки → `{"detail":"Вы вышли из аккаунта"}` |
| GET    | `/auth/me/`     | авториз. | Профиль: `id, email, first_name, last_name, phone, date_joined, is_seller, seller_id` |
| PATCH  | `/auth/me/`     | авториз. | Частичное обновление `first_name/last_name/phone` |
| POST   | `/auth/password/` | авториз. | `{current, next}` → смена, другие сессии инвалидируются |

Анонимный `GET /auth/me/` → **401** `{"detail": "Вы не авторизованы"}` (не 500 и не 403).

Ограничение: auth-эндпоинты — ≥10 запросов/мин на IP (учитывается `X-Forwarded-For`
за прокси) → `429`.

### Демо-аккаунты (после `seed`, пароль `Password123`)

| Email            | Роль | Данные |
| ---------------- | ---- | ------ |
| `seller@uzum.uz` | «Uzum Students» | 1 активный товар + 1 черновик, 1 заказ в `packing` |
| `buyer@uzum.uz`  | покупатель | 2 заказа, отзыв с ответом продавца |
| `electro@uzum.uz`| «Electro House» | 8 товаров |

---

## 🗂 Категории и продавцы

### `GET /categories/`

Конверт без пагинации; `product_count` — число **активных** товаров.

```json
{"count": 10, "page": 1, "page_size": 10, "total_pages": 1, "next": false, "previous": false,
 "results": [{"id": 1, "name": "Электроника", "slug": "elektronika", "emoji": "📱", "color": "#EDE9FF", "product_count": 12}]}
```

### `GET /sellers/`

Сортировка: рейтинг ↓, затем число товаров ↓. Поля: `id, name, slug, logo, rating,
products_count, orders_count, created_at`.

### `GET /sellers/{id|slug}/`

Профиль магазина + **встроенные активные товары** (`products` — массив полных карточек),
`404` если магазин не найден.

---

## 🛍 Товары

### `GET /products/`

Параметры:

| Параметр      | Значение |
| ------------- | -------- |
| `q` / `search`| поиск по `title` и `brand` (icontains) |
| `ids`         | `ids=1,2,3` — только эти товары (перекрывает прочие фильтры) |
| `category`    | `slug` категории |
| `seller`      | `id` продавца |
| `min_price`/`max_price` | фильтр по цене (включительно) |
| `min_rating`  | рейтинг ≥ |
| `discounted=1`| только со скидкой (`old_price > price`) |
| `in_stock=1`  | только `stock > 0` |
| `status`      | `active` (по умолчанию) / `draft` / `all` — чужие черновики невидимы (200, `count: 0`), владелец видит свои |
| `ordering`    | `price`, `-price`, `rating`, `-rating`, `new`, `-created_at`, `discount`, `popular`; без параметра — собственный скоринг (реклама ↓, рейтинг ↓, отзывы ↓, просмотры ↓) |
| `page`        | ≥ 1 |
| `page_size`   | 4…120, по умолчанию 20 |

Ответ дополнительно содержит `facets` (считаются **до** применения фильтра цены, категории —
без учёта фильтра категории):

```json
{"count": 2, ..., "facets": {"price": {"min": 99000, "max": 12990000},
 "categories": [{"id":1,"slug":"elektronika","name":"Электроника","product_count":1}]}}
```

### Карточка товара (поля)

`id, slug, title, description, price, old_price, discount_percent, monthly_payment,
rating, reviews_count, rating_breakdown, delivery_time, stock, in_stock, brand, image,
images, characteristics, is_ad, views, status, created_at, updated_at, seller, category,
has_own_review`

Вычисляемые поля:

- `discount_percent` = `round((old_price − price) / old_price · 100)`, иначе `0`;
- `old_price` = `null`, если скидки нет (или old ≤ price);
- `monthly_payment` — рассрочка 12 мес.: `{"months": 12, "per_month": ceil(price/12/100)·100, "overpay": 0}`;
- `rating_breakdown` — распределение оценок от 5★ до 1★ (денормализованные счётчики);
- `has_own_review` — есть ли отзыв текущего пользователя (cookie-aware);
- `in_stock` — `stock > 0`.

### `GET /products/{id|slug}/`

Чужой черновик → `404`. Свой черновик виден владельцу (поле `status: "draft"`).

### `POST /products/` — создать (только продавец)

`403` `{"detail":"Сначала создайте магазин"}` без магазина. Обязательны `title, description,
price, stock, category_id`. Слаг транслитерируется из названия («новый товар» →
`novyy-tovar`). Успех: `201` `{"detail": "Товар опубликован", ...}`.
Лимит: ≥60 изменяющих запросов/час на пользователя.

### `PATCH /products/{id|slug}/`

Частичное обновление с merge-валидацией (ошибка в одном поле не стирает остальные),
только владелец магазина товара, иначе `403 {"detail":"Это товар другого магазина."}`.

### `DELETE /products/{id|slug}/`

`200 {"detail": "Товар удалён"}` — каскадно удаляет отзывы товара. Чужой → `403`.

### `POST /products/{id|slug}/status/`

`{"status": "active" | "draft"}` — идемпотентно (повтор того же статуса — тоже 200).
Некорректный статус → `400`.

### `POST /products/{id|slug}/view/`

Инкремент просмотров, без авторизации и CSRF: `{"ok": true}`.

### `GET /products/mine/`

Товары моего магазина, включая черновики. Нет магазина →
`{"detail": "У вас пока нет магазина", "results": []}`.

---

## ⭐ Отзывы

### `GET /products/{id|slug}/reviews/`

```json
{"summary": {"count": 2, "average": 4.0, "breakdown": [{"stars": 5, "count": 1}, {"stars": 4, "count": 0}, {"stars": 3, "count": 0}, {"stars": 2, "count": 0}, {"stars": 1, "count": 1}]},
 "can_review": true, "purchases": 1,
 "results": [{"id": 3, "rating": 5, "text": "...", "pros": null, "cons": null,
   "created_at": "...", "updated_at": null, "verified": true, "own": true,
   "author": {"id": 5, "name": "Азиз Юсупов", "initials": "А"}, "seller_reply": "..."}]}
```

- `verified` — есть некупленный-не-отменённый заказ с этим товаром (после отмены заказа флаг снимается);
- `initials` — первая заглавная буква имени; `own` — отзыв текущего пользователя;
- черновик товара: отзывы доступны только владельцу товара, иначе `404`.

### `POST /products/{id|slug}/reviews/`

`{rating: 1..5, text: 15..2000, pros?≤200, cons?≤200}`. Повторный POST — **upsert**:
`201 {"id": N, "updated": false, "detail": "Отзыв опубликован"}`, затем
`200 {... "updated": true}` с тем же `id` (править свой отзыв можно и без покупки).
Без покупки → `403 {"detail":"Чтобы оставить отзыв, сначала купите этот товар"}`.
После записи пересчитываются `product.rating` и `rating_breakdown`.

### `DELETE /reviews/{id}/`

Автор отзыва или владелец магазина товара → `200 {"detail":"Отзыв удалён"}` (агрегаты пересчитаны).

### `POST /reviews/{id}/reply/`

Только продавец товара: `{"reply": "..."}` (5..800 символов) → `200 {"detail":"Ответ опубликован"}`.

---

## 🧾 Заказы

### `PUT /orders/` — превью корзины (без авторизации и CSRF)

Клиент присылает `subtotal` (корзина уже посчитана фронтендом), `delivery_method`,
`promo_code?`. Сервер возвращает пересчитанные суммы:

```json
{"discount": 30000, "delivery_cost": 0, "total": 570000, "promo_valid": true, "promo_label": "Знакомство с маркетплейсом: −5%"}
```

Правила доставки: `pickup` → 0; иначе 0 при `subtotal − discount ≥ 500 000`, иначе `25 000`.
Промокод регистронезависимый, сравнивается с `min_subtotal`; неизвестный → `promo_valid: false, discount: 0`.

### `POST /orders/` — оформить (авторизация + CSRF)

`{items: [{product_id, qty}], delivery_method: pickup|courier, payment_method: cash|card,
pickup_point?|address?, promo_code?, buyer_name?, buyer_phone?, comment?}`

- Суммы **пересчитываются сервером** (клиентские значения игнорируются);
- проверка и списание остатков атомарны (`SELECT ... FOR UPDATE`);
- не хватает остатка → `400` `{"fields": {"items": "«Электросамокат RideMax S3»: на складе всего 1 шт."}}`;
- номер заказа — `UZ-359074` (`UZ-` + 6 цифр);
- успех → `201 {"id": 7, "detail": "Заказ оформлен"}` — полное тело (номер `UZ-XXXXXX`, позиции,
  `timeline`) возвращает `GET /orders/{id}/`;
- каждое изменение статуса пишет событие в `timeline` заказов покупателя и продавца.

### `GET /orders/` — свои заказы (аноним → 401)

### `GET /orders/{id}/`

Покупатель и продавец позиции; чужой → `404` (не раскрываем существование).

### `POST /orders/{id}/status/`

| Действие      | Кто              | Правило |
| ------------- | ---------------- | ------- |
| `advance`     | покупатель **или** продавец позиции | следующий статус вперёд |
| `cancel`      | только покупатель | пока статус не `delivered`/`cancelled`; **возвращает остатки на склад** |

Статусы: `new → packing → shipping → delivered`. Ответ содержит новый статус; полный таймлайн — в `GET /orders/{id}/`. Нарушение правил → `403`/`400`.

---

## 🏪 Кабинет продавца

### `GET /shop/`

Есть магазин → профиль; нет → **200** с телом `null` (не 404).

### `POST /shop/` — создать (идемпотентно)

Первый вызов → `201 {"detail": "Магазин создан"}`, повторный с тем же именем → `200`
`{"detail": "Магазин уже существует"}` (не 409, не дубль).

### `PATCH /shop/` — обновить профиль магазина

Слаг магазина не меняется.

### `GET /shop/orders/` — заказы моего магазина

Позиции заказов, содержащие мои товары, + агрегаты продавца:

```json
{"count": 1, "page": 1, "page_size": 20, "total_pages": 1, "next": false, "previous": false,
 "stats": {"product_count": 8, "draft_count": 1, "review_count": 40, "rating": 4.8,
   "views": 1000, "order_count": 5, "revenue": 4000000, "stock_units": 120},
 "results": [...]}
```

`revenue` — сумма по некупленным заказам (после `cancel` уменьшается).

---

## 🖼 Загрузка файлов

### `POST /uploads/` (multipart, авторизация + CSRF)

Поле `file`: png/jpeg/webp/gif, ≤ 2 МБ → `201`:

```json
{"url": "/api/uploads/lfq3xk0-9f8e2a71.png", "name": "shot.png"}
```

Ключ файла: `<base36 timestamp>-<8 hex><ext по MIME>`. Файлы immutable:
`GET /api/uploads/<key>` отдаётся с `Cache-Control: …, immutable`; изменение/перезапись невозможны.
Ошибки: не картинка/больше 2 МБ → `400`; нет сессии → `401`.

---

## 🩺 Служебные

### `GET /health` (без `/api`-аутентификации)

```json
{"status": "ok", "service": "uzum-market-clone", "backend": "django/5.2", "products": 43,
 "time": "2026-08-30T12:00:00.123Z"}
```

Только чтение БД, никаких изменений.

### `POST /demo/reset/` (авторизация + CSRF)

Возвращает БД к сид-состоянию (43 товара, отзывы, заказы, демо-аккаунты), гасит сессии.
При `UZUM_LOCK_DEMO=1` → `403 {"detail":"Демо-режим заблокирован"}`.

### Статика сида

`GET /products/gen/<name>.svg` — SVG-картинки товаров из сида (`image`/`images` ссылаются сюда).

---

## 🚀 Кэш и производительность

| Тип эндпоинта | `Cache-Control` |
| ------------- | --------------- |
| Публичные списки (`products`, `categories`, `sellers`) | `public, max-age=15, stale-while-revalidate=60` |
| Приватные (`me`, `orders`, `mine`, `shop*`, `uploads POST`) | `no-store, private` |
| Загруженные файлы | `public, max-age=31536000, immutable` |

Seller и category джойнятся `select_related` (без N+1); рейтинг и счётчики
материализованы в полях товара. JSON-тела списков сжимаются gzip при
`Accept-Encoding: gzip`.

---

## ✅ Быстрая самопроверка после деплоя

```bash
B=https://<ваш-домен>
curl -s $B/api/health                          # {"status":"ok",...}
curl -s $B/api/categories/ | jq .count         # 10
# сессия + CSRF:
curl -s -c jar $B/api/auth/csrf/ >/dev/null
T=$(awk '/uzum_csrf/{print $7}' jar)
curl -s -b jar -c jar -H "Content-Type: application/json" -H "X-CSRFToken: $T" \
     -d '{"email":"buyer@uzum.uz","password":"Password123"}' $B/api/auth/login/
curl -s -b jar $B/api/auth/me/ | jq .email     # buyer@uzum.uz
```

Полный прогон контракта — `python scripts/e2e.py` (см. `scripts/README.md`).
