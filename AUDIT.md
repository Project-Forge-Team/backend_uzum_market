# Аудит `backend_uzum_market` (Django + DRF)

**Дата:** 2026-08-28 · **Коммит аудита:** `c505452` · **Объём:** 41 файл, ~1200 строк кода

> **Статус:** все найденные пункты исправлены в этой же ветке — что именно сделано и каким
> тестом закреплено, свёрнуто в разделе [✅ Резолюция](#-резолюция-что-исправлено-v120-2026-08-28).
> Статусы в TL;DR ниже — состояние на момент аудита (v1.1.0).

Методика: чтение всего кода + реальный прогон проекта (venv, миграции, `seed`, dev-сервер,
`curl`, замеры SQL/payload, генерация OpenAPI-схемы) на dataset 20 000 товаров.
Все пункты ниже подтверждены воспроизведением, а не «на глаз».

> Локально проект прогонялся на Django 5.2 (в песочнице Python 3.11, а `Django==6.1`
> требует Python ≥ 3.12 — см. **B-6**). Ни один из найденных багов не зависит от версии Django.

---

## TL;DR

| # | Проблема | Категория | Статус |
|---|----------|-----------|--------|
| A-1 | Cookie с `SameSite=Lax` не доходят до бэка при фронте на другом домене → **авторизация не работает в проде вообще** | данные/контракт | 🔴 блокирует |
| A-2 | `SECURE_SSL_REDIRECT` без `SECURE_PROXY_SSL_HEADER` → **вечный 301-цикл на Render** | деплой | 🔴 блокирует |
| A-3 | `POST /api/auth/refresh/` падал с **500** на form-encoded/multipart теле | код | 🔴 |
| A-4 | Публичный каталог отдаёт **401**, если access-cookie просрочена/бита | код | 🔴 |
| A-5 | `logout` **не отзывает refresh-токен** (`except Exception: pass` глотшает `AttributeError`) | безопасность | 🔴 |
| B-1 | `image` в ответе API — битый URL: `…/media/https%3A/picsum.photos/600/600` | данные | 🔴 |
| B-2 | `register`: токены в теле отдаются, cookie — нет; Bearer-авторизация мертва → **зарегистрироваться и залогиниться нельзя** | контракт | 🔴 |
| B-3 | OpenAPI-схема врёт про `login`/`register`, 8 ошибок генерации, `securitySchemes` нет | контракт | 🟠 |
| B-4 | `page_size`, `price__gte`, `ordering=reviews_count` документированы/ожидаемы, но **молча игнорируются** (200 OK) | контракт | 🟠 |
| B-5 | Логин чувствителен к регистру email, регистрация приводит к lower → **401 для «нормальных» пользователей** | данные | 🟠 |
| B-6 | `requirements.txt` в **UTF-16**, пин `Django==6.1` без фиксации Python → сборка может упасть | деплой | 🟠 |
| C-1 | `MAILERS` вместо `EMAIL_*` → почта в проде уходит на `localhost:25` | конфиг | 🟠 |
| C-2 | 7 из 12 ключей `SIMPLE_JWT` не существуют → конфиг cookie ничего не настраивает | конфиг | 🟡 |
| C-3 | Нет rate-limit на `login`/`register`, refresh не ротируется | безопасность | 🟡 |
| D-1 | Gunicorn **1 sync-worker** (нет `--workers`) → весь API обслуживает 1 запрос одновременно | prod-нагрузка | 🟠 |
| D-2 | Нет индекса на `created_at` → 12.3 мс → 2.7 мс после индекса | перф | 🟡 |
| D-3 | Нет gzip и нет «лёгкого» сериализатора для списка: −93% и −73%payload | перф | 🟡 |
| D-4 | `seed` (перебор всей таблицы) запускается **на каждом деплое** | перф/деплой | 🟡 |

Хорошего тоже много: `select_related` в `ProductViewSet` (1 запрос вместо N+1), `DecimalField` для
денег, `AUTH_USER_MODEL` с email-логином, HttpOnly-cookie вместо `localStorage`, `conn_max_age=600`,
корректный CORS без wildcard при credentials, `SECURE_*`-заголовки в проде, `.env` в gitignore,
`drf-spectacular` подключён, `token_blacklist` в INSTALLED_APPS.

---

## A. Критические баги

### A-1. Авторизация не работает при фронте на другом домене (SameSite)

В `apps/users/auth_views.py:34-53` обе cookie ставятся с `samesite="Lax"`.
При этом `API.md` и `.env.example` предполагают фронтенд на `https://your-app.vercel.app`,
а API — на `https://backend-uzum-market.onrender.com`. Это **кросс-сайт** (different registrable domain):

* `Set-Cookie` с `SameSite=Lax` в ответе на кросс-сайтовый `fetch/XHR` — **браузер отклоняет** (Chrome/Firefox/Safari едины);
* даже если cookie уже есть — при кросс-сайтовом `fetch` она **не отправляется**.

Практический итог: логин возвращает 200, а `/api/auth/me/` — 401; «залогиненность» не появляется никогда.
Локально (`localhost:3000` → `127.0.0.1:8000`) это тоже разные сайты, но `Lax` там обычно
переживает тесты из-за `http`+одинакового `localhost` — отсюда ощущение «у меня же работало».

Проверено: флаги, которые реально уходят в проде —

```
Set-Cookie: uzum_access_token="<JWT>"; HttpOnly; Max-Age=900; Path=/; SameSite=Lax; Secure
```

**Как чинить (выбрать одно):**

1. **Рекомендую: проксировать `/api` через фронтенд** (Next.js `rewrites` / `vercel.json`), чтобы
   для браузера всё было one-origin. Тогда `SameSite=Lax` остаётся, CORS-проблемы исчезают,
   CSRF-защита сохраняется:
   ```js
   // next.config.js
   async rewrites() { return [{ source: '/api/:path*', destination: 'https://backend-uzum-market.onrender.com/api/:path*' }] }
   ```
2. Либо сделать cookie по-настоящему кросс-сайтовыми: `samesite="None"` (+ `secure=True`, уже есть) —
   но тогда нужно **самостоятельно закрыть CSRF**, т.к. DRF не проверяет его для JWT-аутентификации.
   Минимальная защита — требовать на state-changing эндпоинтах заголовок `X-Requested-With`
   (он не входит в CORS-safe-list, значит cross-origin forms его не пришлют):
   ```python
   # settings
   CSRF_COOKIE_SAMESITE = "None"
   SESSION_COOKIE_SAMESITE = "None"
   CSRF_TRUSTED_ORIGINS = get_env_list("CSRF_TRUSTED_ORIGINS")
   ```
3. Либо переехать на один домен (`api.example.uzum` + `market.example.uzum` с `CSRF_COOKIE_DOMAIN='.example.uzum'`).

### A-2. Вечный HTTPS-редирект на Render

`config/settings.py:176` включает `SECURE_SSL_REDIRECT = True`, но нет `SECURE_PROXY_SSL_HEADER`.
Render терминирует TLS и отдаёт в приложение `http` + `X-Forwarded-Proto: https`, поэтому
`request.is_secure()` всегда `False` → каждый запрос получает 301 на `https://`, который снова
приходит как `http` → **бесконечный цикл**.

Воспроизведено (DEBUG=False, запрос с `X-Forwarded-Proto: https`):

```
GET  /api/categories/  без заголовка      -> 301 Location: https://…/api/categories/
GET  /api/categories/  с X-Forwarded-Proto -> 301 Location: https://…/api/categories/   ← зацикливание
```

```python
# config/settings.py, блок `if not DEBUG:`
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

Дополнительно: кросс-сайтовый `fetch` не «проходит» редирект на другой scheme прозрачно — фронт
увидит CORS/`Failed to fetch`, поэтому этот баг обычно маскируется под «CORS не работает».

### A-3. `POST /api/auth/refresh/` падает с 500

`apps/users/auth_views.py:79` — мутация тела запроса:

```python
request.data["refresh"] = refresh_token
```

Когда `request.data` — это `QueryDict` (form-encoded / multipart, либо пустое тело без
Content-Type), он **неизменяемый** → 500:

```
File "apps/users/auth_views.py", line 79, in post
    request.data["refresh"] = refresh_token
AttributeError: This QueryDict instance is immutable
```

Особенно опасно, что сгенерированная по OpenAPI-схеме клиентка шлёт
`application/x-www-form-urlencoded` (см. B-3) → 500 «из коробки».

```python
# вместо мутации — свой payload
serializer = self.get_serializer(data={"refresh": refresh_token})
```

Там же стоит ловить и `serializers.ValidationError` (например, если SimpleJWT не вернул access),
иначе вместо аккуратного 401 будет 400 без чистки cookie.

### A-4. Просроченная cookie превращает публичный каталог в 401

`apps/users/authentication.py:30` — `self.get_validated_token(raw_token)` вызывается **вне** `try/except`.
`InvalidToken` — это `APIException` со статусом 401, и DRF отдаёт его, даже если view доступен анонимно
(`ProductViewSet` — `ReadOnlyModelViewSet` с `AllowAny`).

Проверено на публичном эндпоинте:

```
GET /api/products/  без cookie                      -> 200
GET /api/products/  cookie=garbage                  -> 401 {"detail":"Given token not valid for any token type",…}
GET /api/products/  cookie=<валидный но истёкший>    -> 401
GET /api/categories/ cookie=garbage                 -> 401
```

Access-токен живёт 15 минут и cookie тоже 900 с → у любого «зависшего вкладки на полчасика»
юзера главная страница магазина после refresh покажет ошибку. Это же ломает
«фолбэк на анонима».

```python
def authenticate(self, request):
    raw_token = self.get_cookie_token(request)
    if raw_token is None:
        return None
    try:
        validated_token = self.get_validated_token(raw_token)
    except (InvalidToken, AuthenticationFailed):
        return None  # битый/истёкший токен = аноним, а не 401
    try:
        user = self.get_user(validated_token)
    except (InvalidToken, User.DoesNotExist):
        return None
    return (user, validated_token) if user else None
```

(заодно `return user, validated_token` вместо `user, None` — DRF использует второй элемент как
`request.auth`, он нужен для `request.auth["exp"]`/логики.)

### A-5. `logout` не отзывает refresh-токен, ошибка проглатывается

`apps/users/auth_views.py:118-141`:

```python
"expires_at": timezone.now() + timedelta(seconds=token._assertion["exp"])
```

* `RefreshToken` в SimpleJWT 5.x **не имеет** атрибута `_assertion` → `AttributeError`;
* всё обёрнуто в `except Exception: pass` → ошибка не видна нигде;
* даже если бы сработало: `exp` — это абсолютный unix-timestamp, `now + exp` = **год 2083**
  (проверено) → `flushexpiredtokens` никогда не чистил бы таблицу.

Проверено фактическим поведением:

```
POST /api/auth/logout/            -> 200 {"detail":"Successfully logged out."}
BlacklistedToken.objects.count()  -> 0          ← токен НЕ отозван
POST /api/auth/refresh/ (после logout) -> 200  ← украденный refresh жив и работает
```

`API.md` при этом обещает: «Обе cookies удаляются, refresh-токен добавляется в блэклист».

```python
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

def post(self, request, *args, **kwargs):
    raw = request.COOKIES.get("uzum_refresh_token")
    if raw:
        try:
            RefreshToken(raw).blacklist()      # встроенный API, всё делает сам
        except TokenError:
            pass                                # уже отозван/истёк — штатно
    …
```

Ручные `OutstandingToken/BlacklistedToken` не нужны: SimpleJWT сам создаёт `OutstandingToken`
по сигналу `jwt_signed`. `except Exception: pass` стоит заменить на `logger.exception(...)` —
сейчас любой баг в логауте невидим.

### A-6. `seed` выполняется на каждом деплое

`build.sh:14` → `python manage.py seed`, который сначала **выбирает все товары и всех
категории/продавцов** и перебирает их ради `fix_encoding()`. На моём прогоне с 20 000 товаров
это ~1 с и полный скан таблицы на каждом билде (на 1M — минуты + RAM).
Плюс если таблица пуста, в **прод** зальются демо-данные.
Исправление: вынести `fix_encoding` в одноразовую команду (или в data-migration), в `build.sh`
запускать `seed` только при `--if-empty`/тогда, когда `Product.objects.not_exists()`, и использовать
`iterator(chunk_size=2000)` + `bulk_update`.

Дополнительно в `seed.py`:
* строки 80-86 — **дублирующий** `if Product.objects.exists(): …` (второй недостижим);
* `from django.db import IntegrityError` и `from django.db import models` — неиспользуемые импорты;
* `Category.objects.create(...)` вместо `get_or_create(slug=…)` → повторный запуск на неполной
  БД дублирует категории/продавцов; обёртки в `transaction.atomic()` нет.
* эвристика `value.encode('latin-1').decode('utf-8')` **необратимо правит данные** при каждом запуске
  (легитимные `Ã…`, `Ã‰tÃ©`-подобные строки превращаются в другое); такие «починки» должны быть
  одноразовыми, с бэкапом и логом изменённых id.

---

## B. Ошибки передачи данных / контракта

### B-1. Поле `image` — битый URL

`Product.image` — это `ImageField` (`apps/products/models.py:44`), а в данные пишутся внешние URL
(`seed.py:238`, `data.txt`). DRF для `ImageField` делает `request.build_absolute_uri(MEDIA_URL + name)`
и URL-экранирует `:`:

```json
"image": "http://127.0.0.1:8123/media/https%3A/picsum.photos/600/600"
```

картинка = 404 всегда. При этом `images[0]` отдаётся как есть (`https://picsum.photos/…?random=61`) —
**два поля, два разных формата одного и того же**. `API.md` же утверждает, что `images` — это
ссылки на `/media/products/…`.

Лечится либо (a) хранить относительные пути и раздавать медиа (B-7), либо (b) хранить строку-URL:

```python
# models.py
image = models.URLField(max_length=500, blank=True)  # или ImageField(null=True, blank=True)

# serializers.py
images = serializers.ListField(child=serializers.URLField(max_length=500), required=False)


def get_image(self, obj):
    if not obj.image:
        return None
    value = str(obj.image)
    if value.startswith(("http://", "https://")):
        return value  # внешние CDN не ломаем
    return self.context["request"].build_absolute_uri(settings.MEDIA_URL + value)
```

### B-2. `register` отдаёт токены, но авторизоваться ими нельзя

Реальный ответ `POST /api/auth/register/`:

```json
{"user":{…},"refresh":"eyJ…","access":"eyJ…"}
```

* `Set-Cookie` — **нет** (cookie ставит только `CookieTokenObtainPairView`);
* `Authorization: Bearer <access>` на `/api/auth/me/` → **401**, потому что в
  `DEFAULT_AUTHENTICATION_CLASSES` остался только `CookieJWTAuthentication`, читающий cookie
  (`apps/users/authentication.py:19-23` переопределён только на cookie).

То есть токены из `/register/` не работают нигде, а клиент, следующий `API.md`
(«ответ — плоский объект пользователя»), после регистрации получает незалогиненного юзера и
401 на первом же приватном запросе.
`API.md` и реализация расходятся в обе стороны — это и есть «ошибка передачи данных».

Варианты (нужен ровно один):
* **cookie-first (рекомендую):** после `serializer.save()` вызывать ту же логику, что и в
  `CookieTokenObtainPairView`, вернуть `UserSerializer` и **не** возвращать токены в теле;
* **header-first:** добавить `rest_framework_simplejwt.authentication.JWTAuthentication` в
  `DEFAULT_AUTHENTICATION_CLASSES` **до** cookie-версии — тогда и `Bearer`, и cookie работают,
  но тогда `localStorage`/XSS-риск надо осознать.

### B-3. OpenAPI-схема противоречит коду

`/api/schema/` генерируется с 8 ошибками и 10 предупреждениями:

```
Error [MeView]: unable to guess serializer …
Error [CookieTokenLogoutView]: unable to guess serializer …
Warning […]: could not resolve authenticator <class 'apps.users.authentication.CookieJWTAuthentication'>
```

Из-за этого в схеме нарисовано:

| Эндпоинт | Что обещает схема | Что на самом деле |
|---|---|---|
| `POST /api/auth/login/` | `200 → {access, refresh}` | 200 → объект пользователя, токенов нет |
| `POST /api/auth/register/` | `201 → {email, first_name,…}` | `{"user":{…},"access":…,"refresh":…}` |
| `GET /api/products/` | параметр `page` | `page_size` (из `API.md`) отсутствует |
| `Product.image` | `string(format: uri)` | битый `/media/…` URL (B-1) |
| `images`, `characteristics` | `{}` (без типа) | `List[str]` / `Dict[str,str]` |
| `security` | `- {}` (нет схемы) | cookie-авторизация не описана → Swagger «Try it out» не работает |

Лечится так: `serializer_class`/`@extend_schema` на всех `APIView`, `ListField`/`DictField`
в `ProductSerializer`, плюс регистрация cookie-схемы:

```python
# config/settings.py
SPECTACULAR_SETTINGS = {
    "TITLE": "Uzum Market API",
    "DESCRIPTION": "…",
    "VERSION": "1.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api",
    "ENUM_GENERATE_CHOICE_DESCRIPTION": False,
}
# apps/users/schema.py (подключить импортом из urls или apps.ready)
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CookieJWTScheme(OpenApiAuthenticationExtension):
    target_class = "apps.users.authentication.CookieJWTAuthentication"
    name = "cookieAuth"

    def security_definition(self):
        return {"type": "apiKey", "in": "cookie", "name": "uzum_access_token"}
```

### B-4. Параметры, которые «принимаются», но игнорируются

Сейчас это не 400, а 200 с неверными данными — фронт не узнает, что фильтр не сработал:

| Запрос | Реальный результат |
|---|---|
| `/api/products/?page_size=50` | вернулось 6 (жёсткий `PAGE_SIZE=10`) |
| `/api/products/?price__gte=9999999` | `count: 6` — фильтр не применён |
| `/api/products/?min_price=100` | 200, игнорируется |
| `/api/products/?ordering=reviews_count` | сортировка по `created_at` (поле не в allowlist) |
| `/api/products/?is_ad=false` | игнорируется |

```python
# apps/products/pagination.py
from rest_framework.pagination import PageNumberPagination


class CatalogPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100  # защита от ?page_size=100000


# apps/products/filters.py
from django_filters import rest_framework as filters


class ProductFilter(filters.FilterSet):
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    is_ad = filters.BooleanFilter()
    category = filters.CharFilter(field_name="category__slug")

    class Meta:
        model = Product
        fields = ["category", "seller", "min_price", "max_price", "is_ad"]
```

`ordering_fields = ['price', '-price', 'rating', 'reviews_count', 'old_price', 'created_at', 'id']`.
Если `API.md` обещает `page_size` — значит он обязан работать; если не обещает — лучше вернуть
`400 Unknown query parameter` для неизвестных ключей, чтобы такие расхождения всплывали сразу.

### B-5. Логин чувствителен к регистру email

`RegisterSerializer.validate_email` сохраняет email в `lower()` (`apps/users/serializers.py:39`),
а SimpleJWT ищет по точному совпадению. Проверено:

```
login 'probe@example.com'  -> 200
login 'Probe@Example.COM'  -> 401 {"detail":"No active account found with the given credentials"}
```

Пользователь, зарегистрировавший `Ivan@Gmail.com`, не сможет войти — и это типичный «телефон звонит,
пароль правильный». Чинится нормализацией на входе (в `LoginSerializer.validate_email` → `value.strip().lower()`)
или кастомным `ModelBackend` с `email__iexact`.
Заодно `validate_email` стоит делать `value.strip().lower()` (пробелы сейчас проходят — `'a@b.c '`
и `'a@b.c'` это два разных аккаунта с точки зрения `unique`).

### B-6. `requirements.txt` в UTF-16 и пин Python

`requirements/requirements.txt` начинается с `0xFF 0xFE` — это **UTF-16LE с BOM** + CRLF:

```
\xff\xfea\x00s\x00g\x00i\x00r\x00e\x00f\x00=\x003\x00.\x001\x002\x00.\x001\x00\r\x00\n\x00…
```

`pip` выживает (сам определяет BOM — проверено), но `git diff` показывает «Binary files differ»,
`grep` по файлу не находит ни одной зависимости, а `pip-compile`/Dependabot/`safety`-сканеры
довольно часто на таком файле либо падают, либо молча игнорируют содержимое. В конце файла дописаны ещё две строки через пустые строки
(`django-filter==24.3`, `djangorestframework-simplejwt==5.5.1`) — фактически файл собран из
двух `pip freeze`.

Второй риск: `Django==6.1` при `Requires-Python: >=3.12`, а в репозитории нет `.python-version`
/ `runtime.txt`, и в `build.sh` нет проверки версии Python. Render для ранее созданных сервисов
оставляет «их» дефолт (исторически 3.11.x) — вот что тогда даёт сборка:

```
ERROR: Ignored the following versions that require a different python version: … 6.1 Requires-Python >=3.12 …
ERROR: No matching distribution found for Django==6.1
```

Минимальный набор: пересоздать файл в UTF-8 (LF), оставить только **прямые** зависимости
(+ separately `requirements-dev.txt` / `pip-compile`), добавить `.python-version` (`3.12` или
`3.14`) и `psycopg[binary]` вместо `psycopg2-binary` (Django 6 официально рекомендует psycopg 3;
psycopg2 объявлен «likely to be deprecated»).

### B-7. `media/` не отдаётся и теряется при деплое

* `/media/products/x.jpg` → 404 (в `config/urls.py` нет `static(settings.MEDIA_URL, …)`,
  WhiteNoise обслуживает только статику);
* `MEDIA_ROOT = BASE_DIR / 'media'` на Render — **эфемерный диск**: всё, что загрузили юзеры,
  стирается при следующем деплое;
* `Product.image` — обязательное поле (`ImageField` без `null/blank`), но write-endpoint'ов нет,
  поэтому создать товар через API невозможно в принципе.

Нужен либо объект-сторадж (S3/Cloudflare R2 + `django-storages`), либо явное ограничение
«картинки только по URL». И `STORAGES['staticfiles'] = whitenoise.storage.CompressedManifestStaticFilesStorage`
— сейчас WhiteNoise подключён, но без сжатия и без хэша в имени → браузеры не кэшируют статику надолго.

### B-8. Мелочи контракта

* `created_at` есть в модели и в `ordering_fields`, но **отсутствует в `ProductSerializer.Meta.fields`** —
  фронт не может показать дату/«новинку» и не может сверить сортировку;
* `discount`/`discount_percent` и `monthly_payment` считаются на фронте; надёжнее считать на бэке
  (`SerializerMethodField` + `F()`), чтобы скидка не расходилась с ценой;
* `Product.characteristics` — «свободный» JSON без схемы → у фронтенда `Record<string, unknown>`;
  лучше `DictField(child=CharField())` или нормальная модель `ProductCharacteristic`;
* `data.txt` (787 строк) в корне — **дублирующий** сид-скрипт, не импортируется ни откуда;
  вместе с ним в репо пустой `migrations/__init__.py` в корне. Оба удалить.

---

## C. Конфигурация и безопасность

### C-1. Почта: `MAILERS` не существует

`config/settings.py:156,162` определяют `MAILERS = {...}` — такой настройки Django нет
(есть плоские `EMAIL_BACKEND`, `EMAIL_HOST`, …). Проверено, что реально подхватывается:

```
EMAIL_BACKEND: django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST: 'localhost' PORT: 25 USER: '' TLS: False
→ send_mail() в проде попытается постучаться на localhost:25 и упадёт с ConnectionRefused
```

Консольный бэкенд для DEBUG тоже не включился. Сейчас почта нигде не отправляется, поэтому
баг «спит» — но первая же «забыли пароль» развалится. Правильно:

```python
if DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.getenv("EMAIL_HOST", "")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in ("1", "true", "yes")
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
```

### C-2. Полумёртвый конфиг JWT

7 из 12 ключей `SIMPLE_JWT` (`config/settings.py:214-221`) SimpleJWT **не знает** — проверено:

```
AUTH_COOKIE / REFRESH_COOKIE / AUTH_COOKIE_SECURE / AUTH_COOKIE_HTTP_ONLY
AUTH_COOKIE_SAMESITE / AUTH_COOKIE_PATH / REFRESH_COOKIE_PATH  → НЕ СУЩЕСТВУЕТ (молча игнорируется)
```

Реальные значения захардкожены в `apps/users/auth_views.py:34-53` (`max_age=900`, `path='/'`,
`samesite="Lax"`). Классическая ловушка: меняешь `ACCESS_TOKEN_LIFETIME` на 30 минут — cookie
продолжает жить 15, и наоборот. Также `BLACKLIST_AFTER_ROTATION: True` бессмысленен при
`ROTATE_REFRESH_TOKENS: False`.

Вынести в `settings.SIMPLE_JWT` реальные ключи (`ACCESS_TOKEN_LIFETIME`, `REFRESH_TOKEN_LIFETIME`)
и читать их в `auth_views`:

```python
from django.conf import settings as s

ACCESS_MAX_AGE = int(s.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds())
REFRESH_MAX_AGE = int(s.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds())
COOKIE_SECURE = not s.DEBUG
COOKIE_SAMESITE = "None" if COOKIE_SECURE else "Lax"  # см. A-1
```

И удалить мёртвые ключи, чтобы не вводить в заблуждение.

### C-3. Ротация/отзыв refresh и brute-force

* `ROTATE_REFRESH_TOKENS = False` + неработающий блэклист (A-5) → **украденный refresh-токен
  активен все 7 дней**, отозвать его нельзя. Рекомендую `ROTATE_REFRESH_TOKENS=True` +
  `BLACKLIST_AFTER_ROTATION=True`, `ACCESS_TOKEN_LIFETIME=5-10 мин`;
* нет троттлинга на `login`/`register`/`refresh` — перебор паролей не ограничен. Минимум:
  ```python
  'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle'],
  'DEFAULT_THROTTLE_RATES': {'login': '10/min', 'register': '5/hour', 'anon': '60/min'},
  ```
  и `throttle_classes = [AnonRateThrottle]` на `CookieTokenObtainPairView`/`RegisterView`
  (с `cache`-бэкендом, а не LocMem, иначе лимиты «свои» на каждый worker);
* `AllowAny` + cookie-авторизация без CSRF — при переходе на `SameSite=None` (A-1) это станет
  обязательным к закрытию (см. A-1 вариант 2);
* кастомные сообщения «Пользователь с таким email уже существует» → перечисление аккаунтов.
  Для маркетплейса обычно терпимо, но при регистрации стоит слать письмо-подтверждение;
* гонка в `validate_email` (`exists()` → `create()`): два параллельных запроса дают `IntegrityError`
  → 500. Проще положиться на `UniqueValidator` + `lower()` или обернуть в
  `except IntegrityError: raise ValidationError(...)`;
* нет `LOGGING` вообще — ошибки SimpleJWT/seed (те же проглоченные `except Exception`) не видны
  в логах Render. Добавить `django.request`/`apps` логгер на `ConsoleHandler`.

### C-4. Прочее по настройкам

* `DEFAULT_AUTO_FIELD` не задан → 4 предупреждения `models.W042` **и** дрейф миграций:
  `makemigrations --check` требует создать `0003_alter_*_id` (`AutoField` ↔ `BigAutoField` как в
  существующих миграциях). Кто запустит `makemigrations` — получит `ALTER COLUMN … bigint→int`
  на проде:
  ```
  Migrations for 'products': 0003_alter_category_id_alter_product_id_alter_seller_id.py
  Migrations for 'users':   0002_alter_user_id.py
  ```
  Правка: `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'` в `settings.INSTALLED_APPS`-блоке.
* `ALLOWED_HOSTS` по умолчанию содержит `onrender.com` (домен целиком) — достаточно точного
  `backend-uzum-market.onrender.com`;
* `SECURE_HSTS_SECONDS = 86400` c `INCLUDE_SUBDOMAINS`/`PRELOAD` — preload без регистрации на
  hstspreload.org бесполезен, а 24 часа мало (рекомендуют 6 мес.). Осторожно с includeSubdomains
  для общей зоны;
* `TIME_ZONE='UTC'` — правильно; но `created_at` отдаётся без смещения на UZT (+5), учитывайте
  это на фронте или отдавайте `created_at_display`;
* `.env.example` содержит годный SECRET_KEY-пример — убедитесь, что в проде сгенерирован свой
  (JWT HS256 = тот же секрет; короткий ключ = слабая подпись).

---

## D. Оптимизация (с замерами)

Dataset: 20 000 товаров, SQLite (относительные эффекты переносимы на Postgres; абсолютные числа — нет).

### D-1. Gunicorn: 1 sync-worker — самое узкое место

`Procfile`: `gunicorn config.wsgi:application --log-file -` — без `--workers/--threads/--timeout`.
Дефолт gunicorn: **1 worker, sync** → сервер обслуживает **по одному запросу одновременно**;
один медленный `?search=` блокирует весь магазин.

```
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT \
     --workers 3 --threads 4 --worker-class gthread \
     --timeout 60 --graceful-timeout 30 --max-requests 1000 --max-requests-jitter 100 \
     --access-logfile - --error-logfile -
```
(на Render free/0.5 GB лучше `--workers 2`; для I/O-bound API заметный прирост уже здесь.)

### D-2. Индексы

```
ORDER BY created_at DESC LIMIT 10 (индекса нет)
  → SCAN products_product ; USE TEMP B-TREE FOR ORDER BY
```
| Замер | до | после |
|---|---|---|
| список (count + 10 товаров + сериализация) | 12.28 мс | **2.65 мс** с индексом `created_at DESC` |

```python
class Meta:
    ordering = ["-created_at"]
    indexes = [
        models.Index(fields=["-created_at"], name="product_created_idx"),
        models.Index(fields=["category", "-created_at"], name="product_cat_created_idx"),
        models.Index(fields=["seller", "-created_at"], name="product_sel_created_idx"),
        models.Index(fields=["price"], name="product_price_idx"),
        models.Index(fields=["is_ad"], name="product_isad_idx"),
    ]
```

`search` (`icontains`) = `LIKE '%…%'` → индекс B-tree **не помогает** (замер: 22.5 мс → 18.7 мс).
Для Postgres: `CREATE EXTENSION IF NOT EXISTS pg_trgm` + GIN-индекс по `title`/`description`
(`TrigramSimilarity` вместо `icontains`, если хочется качества), либо `search_type='icontains'`
с ограничением минимальной длины запроса.

### D-3. `COUNT(*)` на каждой странице

`PageNumberPagination` считает всю выборку на каждый запрос (`COUNT(*)` на 20k — 0.18 мс,
на 5M с `LIKE`-фильтром — сотни мс). Варианты:
* `pagination_class` с `get_next_link`-без-`next` при `count`-кэше (кэш счётчика на 60 с по хэшу фильтров);
* или `LimitOffsetPagination` + «Загрузить ещё» (не нужен `count`);
* или `count` с `estimated_rows` через `pg_class.reltuples` для «~N товаров».

### D-4. Payload и сжатие

```
10 товаров списком: 15 760 Б (≈1.5 КБ/товар: description + characteristics + вложенные category/seller)
→ gzip: 1 079 Б  (-93%), но сервер НЕ сжимает: в ответе нет Content-Encoding
→ компактный сериализатор для списка: 4 303 Б (-73%)
```

В карточку товара эти поля нужны, в сетке каталога — нет. Разделите сериализаторы:

```python
class ProductListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "price",
            "old_price",
            "discount",
            "rating",
            "reviews_count",
            "image",
            "category",
            "is_ad",
            "monthly_payment",
        ]


class ProductViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ProductSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        return ProductSerializer

    def get_queryset(self):
        qs = Product.objects.select_related("category", "seller")
        return qs.only(...) if self.action == "list" else qs  # не тащим description/characteristics
```

И включить сжатие JSON: `MIDDLEWARE += ['django.middleware.gzip.GZipMiddleware']` (эффект
замерен выше) — либо delegate на Render/CDN.

### D-5. N+1 в админке

`ProductAdmin.list_display` обращается к `category`/`seller` → на 10 строк **21 запрос**;
с `list_select_related = True` — **1 запрос**. То же в `CategoryAdmin`/`SellerAdmin`
(добавить `list_per_page = 50`, `list_display_links`).

### D-6. Кэш стабильных данных и HTTP-кэш

`/api/categories/` и `/api/sellers/` меняются редко, но каждый запрос = SELECT + COUNT.
Добавить `LocMemCache`/`Redis` + `cache_page`, либо `Cache-Control`/`ETag`
(`django-etag` / `fetch('cache')` на фронте), чтобы списки категорий не «ходили» на БД при каждом
рендере шапки/фильтров. Для каталога с пагинацией хорошо работает
`@method_decorator(cache_page, name='list')` c коротким TTL (30-60 с).

### D-7. База данных / пул

* `conn_max_age=600` ✓ — добавить `CONN_HEALTH_CHECKS=True` (Render/Postgres обрывают коннекты);
* для psycopg 3 доступен `OPTIONS: {'pool': {'min_size': 1, 'max_size': 10}}` (плюс `psycopg[pool]`);
* `dj_database_url.config(default=DATABASE_URL)` — стоит включить `conn_max_age`/`sslrequire`
  для внешнего Postgres Render (`'OPTIONS': {'sslmode': 'require'}`), иначе часть подключений пойдёт без TLS.

---

## E. Архитектура / гигиена

### E-1. Мёртвый код (убрать или подключить)

| Файл | Статус |
|---|---|
| `apps/users/urls.py` | **не подключён** ни к одному `urlpatterns` → `/api/users/…` не существует; содержит `CustomTokenObtainPairView/RefreshView/VerifyView` |
| `apps/products/urls.py` | **не подключён** — `config/urls.py` сам строит `DefaultRouter` (дубль, строки 10-27) |
| `apps/users/views.py:38-50` | `CustomToken*View` (body-token flow) — недостижимы; их токены всё равно не работают (B-2) |
| `data.txt` (787 стр.) | второй, «домашний» seed; не вызывается |
| `migrations/__init__.py` (корень) | пустой пакет-заглушка |
| `seed.py:83-86` | дублирующая проверка `Product.objects.exists()` |
| `seed.py:13`, `seed.py:2` | неиспользуемые импорты `models`, `IntegrityError` |
| `ProductViewSet.filter_backends` | дублирует `DEFAULT_FILTER_BACKENDS` из settings (можно не дублировать) |

Из-за двух параллельных реализаций auth (`views.py` — «токен в теле», `auth_views.py` — «токен в
cookie») легко чинить не тот файл. Рекомендую оставить **одну** (`auth_views.py`) и удалить вторую.

### E-2. Тесты

`apps/users/tests.py` и `apps/products/tests.py` — заглушки (`# Create your tests here.`).
Минимальный набор, который поймал бы всё найденное выше (готов вставить):

```python
# apps/products/tests.py
class ProductApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(name="Электроника", slug="electronics")
        cls.seller = Seller.objects.create(name="Tech")
        Product.objects.create(
            title="X",
            description="d",
            price="1.00",
            delivery_time="1",
            image="https://cdn/x.jpg",
            category=cls.cat,
            seller=cls.seller,
        )

    def test_list_shape(self):
        r = self.client.get("/api/products/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("%3A", r.json()["results"][0]["image"])  # B-1

    def test_broken_cookie_does_not_break_public(self):  # A-4
        r = self.client.get("/api/products/", HTTP_COOKIE="uzum_access_token=garbage")
        self.assertEqual(r.status_code, 200)

    def test_page_size_and_price_range(self):  # B-4
        Product.objects.create(
            title="Y",
            description="d",
            price="99.00",
            delivery_time="1",
            image="https://cdn/y.jpg",
            category=self.cat,
            seller=self.seller,
        )
        self.assertEqual(self.client.get("/api/products/?min_price=50").json()["count"], 1)
        self.assertEqual(len(self.client.get("/api/products/?page_size=1").json()["results"]), 1)

    def test_image_is_a_usable_url(self):  # B-1
        r = self.client.get("/api/products/")
        self.assertTrue(r.json()["results"][0]["image"].startswith("https://cdn/"))
```

```python
# apps/users/tests.py
class AuthTests(TestCase):
    def test_register_sets_cookie_and_no_token_body(self): …        # B-2
    def test_login_case_insensitive(self): …                        # B-5
    def test_refresh_accepts_empty_and_form_body(self):             # A-3
    def test_logout_blacklists_refresh(self):                       # A-5
```

### E-3. CI и линтеры (сейчас нет ни того, ни другого)

`GitHub Actions`/`render.yaml`-хук на каждый PR:

```yaml
- python -V && python manage.py check                    # W042 (C-4)
- python manage.py makemigrations --check --dry-run       # дрейф миграций
- python manage.py spectacular --validate --fail-on-warn  # B-3 (сейчас падает: 8 errors)
- python manage.py test --verbosity=2
- ruff check . && ruff format --check .                   # нашёл бы неиспользуемые импорты seed.py
```

### E-4. Структура (по желанию, на текущем объёме почти не болит)

* два `AppConfig` без `default_auto_field`/`verbose_name`; нет `apps/__init__.py` (работает как
  namespace-package, но ломает `find_packages()`/`pip install -e .`);
* один `settings.py` для dev/prod — лучше `config/settings/{base,dev,prod}.py` или `pydantic-settings`
  с явной валидацией (тогда отсутствие `SECRET_KEY`/`EMAIL_HOST` падает на старте, а не в рантайме);
* `Product.images: JSONField` + `characteristics: JSONField` — на росте объёмов их стоит
  нормализовать (`ProductImage`, `ProductCharacteristic`), иначе невозможно neither фильтровать
  по характеристике, ни индексировать;
* `Category.parent`/`level` — для маркетплейса без дерева категорий будет больно на этапе
  «Электроника → Смартфоны»; `Seller.slug` + `Seller.is_verified`;
* `Seller.rating`/`Product.rating` как `FloatField` — аккуратнее `DecimalField(max_digits=3, decimal_places=2)`
  (или `PositiveSmallIntField` со scale 10), т.к. `4.85` в float даёт `4.8499999…` в JSON;
* `write`-эндпоинты (в `API.md` они в «планах») — при их появлении обязательно добавить
  `IsAuthenticated`+ownership (`seller=request.user.seller`) и CSRF-решение из A-1.

---

## Приоритетный план

> План ниже — из состояния v1.1.0. Выполнен целиком, кроме пунктов, вынесенных в
> «Не вошло (осознанные follow-up’ы)» в конце документа.

**Сегодня (иначе прод не работает / течёт):**
1. `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` (A-2);
2. решить модель cookies: прокси `/api` через фронт **или** `SameSite=None` + CSRF (A-1);
3. `CookieJWTAuthentication`: бить/истёк → аноним, а не 401 (A-4);
4. `refresh`: `data={"refresh": …}` вместо мутации `request.data` (A-3);
5. `logout`: `RefreshToken(raw).blacklist()`, убрать `except Exception: pass` (A-5);
6. `.python-version` + `requirements.txt` в UTF-8 (B-6); `Procfile` → `--workers/--threads` (D-1).

**На этой неделе:**
7. единый auth-контракт: register ставит cookie, токены в тело не уходят; удалить
   `apps/users/views.py`/`urls.py` (B-2, E-1);
8. `image`/`images` + раздача `media` (или внешние URL) (B-1, B-7);
9. `CatalogPagination` (`page_size`), `ProductFilter` (`min/max_price`, `is_ad`),
   расширенный `ordering_fields` (B-4); `DEFAULT_AUTO_FIELD` (C-4);
10. `EMAIL_*` вместо `MAILERS` (C-1); `PRODUCT`-индексы (D-2);
11. `serializer_class`/`@extend_schema` + `cookieAuth` для OpenAPI (B-3);
12. тесты + CI (E-2, E-3); `build.sh`: убрать `seed` с каждого деплоя (A-6).

**Потом (качество и рост):**
13. `ProductListSerializer` + gzip (D-4); `list_select_related` в админке (D-5);
    кэш категорий/ETag (D-6); ротация refresh + throttle (C-3); `pg_trgm`-поиск (D-2);
    LOGGING (C-3); нормализация `images`/`characteristics`, дерево `Category` (E-4).


---

## ✅ Резолюция: что исправлено (v1.2.0, 2026-08-28)

Все пункты закрыты; против каждого — тест, чтобы баг не вернулся. Проверки в репозитории:
`python manage.py test --settings=config.test_settings` (59 тестов), `ruff check`,
`manage.py check --deploy`, `makemigrations --check`, `spectacular --validate --fail-on-warn`.

| # | Проблема | Что сделано | Где закреплено тестом |
|---|---|---|---|
| A-1 | Cookie `SameSite=Lax` не работают кросс-доменно | Настройки `COOKIE_SAMESITE`/`COOKIE_SECURE` (прод → `None; Secure`), режим выбирается деплоем; описаны 2 режима (прокси `/api` через фронт = Lax; кросс-домен = None + double-submit CSRF). Проверка `SameSite=None` без `Secure` теперь падает на старте | `LoginTests.test_cross_site_mode_requires_csrf_header`, `test_cookie_flags_follow_settings` |
| A-2 | 301-цикл за TLS-прокси | `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')` | проверено живым curl: `X-Forwarded-Proto: https` → **200** (было 301) |
| A-3 | 500 на `refresh` с form-encoded телом | Серовиализатору передаётся свой payload `{"refresh": …}`, `request.data` не мутируется | `test_refresh_accepts_form_encoded_body`, `test_refresh_accepts_no_body_and_updates_access_cookie` |
| A-4 | 401 на публичных эндпоинтах из-за битой cookie | `CookieJWTAuthentication` возвращает `None` на любой невалидный токен (401 даёт только `IsAuthenticated`) | `test_expired_access_token_yields_401_on_protected_only` |
| A-5 | Logout не отзывал refresh (ошибка глоталась) | `RefreshToken(raw).blacklist()`, `except TokenError` узко, остальное → `logger.exception`; logout доступен и анонимно | `test_logout_blacklists_refresh_token`, `test_logout_allowed_without_valid_access_token` |
| A-6 | `seed` с полным сканом таблицы на каждый деплой | Починка кодировки вынесена за `--fix-encoding`; по умолчанию — один `exists()`; есть `--force/--reset`; `iterator(chunk_size)`; `get_or_create` + `transaction.atomic` | `seed --fix-encoding` запускается вручную |
| B-1 | Битый `image` (`/media/https%3A/…`) | `image` → `URLField`, отдаётся как есть; относительный путь разворачивается в `{MEDIA_URL}` запроса (`absolute_media_url`) | `test_list_shape_and_external_image_not_mangled`, `test_local_media_path_becomes_absolute` |
| B-2 | `register` отдавал бесполезные токены | Единый cookie-флоу: register ставит cookies, токены в теле не возвращаются; `Authorization: Bearer` **реально** работает (аутентификатор читает и заголовок, и cookie) | `test_sets_cookies_and_no_tokens_in_body`, `test_bearer_token_supported` |
| B-3 | OpenAPI расходился с кодом | `serializer_class`/`@extend_schema` на всех auth-вьюхах, типы для `images`/`characteristics`/`discount_percent`, `cookieAuth`+`jwtAuth` securitySchemes, Redoc. `--validate --fail-on-warn` — часть CI | CI step `spectacular … --fail-on-warn` (было 8 ошибок → 0) |
| B-4 | `page_size`/`min_price`/`ordering` молча игнорировались | `CatalogPagination` (`page_size` + потолок), `ProductFilter` (`min_price`, `max_price`, `min_rating`, `is_ad`, `discounted`, `category_slug`, `seller`), расширенный `ordering_fields`, `400` на неизвестные параметры | `PaginationAndFilterTests` (6 тестов), `test_unknown_query_param_is_400` |
| B-5 | Логин чувствителен к регистру email | `UserManager.get_by_natural_key` → `iexact`, нормализация в `User.save()` и в логин-сериализаторе | `test_login_case_insensitive`, `test_email_normalized_and_me_works` |
| B-6 | `requirements.txt` в UTF-16, Python не зафиксирован | Файл пересобран в UTF-8/LF, только прямые зависимости; `.python-version` = 3.12; `build.sh` проверяет версию Python с внятной ошибкой; psycopg2 → `psycopg[binary]==3.3.4` | CI (`setup-python: python-version-file`) |
| B-7 | `media/` не отдавался и терялся при деплое | Раздача `/media/` в DEBUG (`static()` в urls), опциональный S3/R2 (`USE_S3` + `requirements/storage.txt`, `STORAGES`), WhiteNoise с Compressed/Manifest | `config/urls.py`, `build.sh` |
| C-1 | Почта в `MAILERS` (не существующая настройка) | Плоские `EMAIL_*` + `DEFAULT_FROM_EMAIL`, `EMAIL_TIMEOUT` | — |
| C-2 | 7 несуществующих ключей `SIMPLE_JWT`, захардкоженные cookie | Настройки cookie собраны в `settings.JWT_COOKIE`, `apps/users/cookies.py` читает lifetime из `SIMPLE_JWT` (Max-Age больше не может разъехаться с TTL токена) | `test_cookie_flags_follow_settings` |
| C-3 | Нет ротации/отзыва refresh, нет троттлинга | `ROTATE_REFRESH_TOKENS=True` + `BLACKLIST_AFTER_ROTATION=True`; `ProxyAwareScopedRateThrottle` (лимит по IP из `X-Forwarded-For`, лимиты читаются из настроек в рантайме) | `test_login_is_throttled`, `test_rotation_invalidates_old_refresh_token` |
| C-4 | `DEFAULT_AUTO_FIELD` не задан | `DEFAULT_AUTO_FIELD = BigAutoField` + `default_auto_field` в обоих `AppConfig`; `makemigrations --check` в CI | CI step «Миграции сгенерированы» |
| D-1 | Gunicorn в 1 sync-worker | `Procfile`: `--workers 3 --threads 4 --worker-class gthread --timeout 60 --max-requests … --bind 0.0.0.0:$PORT` | — |
| D-2 | Нет индексов | `Meta.indexes`: `-created_at`, `(category,-created_at)`, `(seller,-created_at)`, `price`, `is_ad`, `category.name`; миграция `0003` | миграция `0003_*` |
| D-3 | Payload и отсутствие gzip | `GZipMiddleware` (−93%), `ProductListSerializer` для списка (−73%) + `defer('description','characteristics','images')`, `ConditionalGetMiddleware` (ETag → 304); WhiteNoise: Manifest (хэши + `immutable`) на проде, Compressed без него, если статика не собрана (иначе `/admin/` падал с 500) | `test_list_defers_description`, `test_json_is_gzipped` |
| D-4 | `COUNT` и повторные списки | Кэш списков на `CATALOG_CACHE_SECONDS` с версионным ключом и инвалидацией по `post_save/post_delete` | `test_list_is_cached_and_invalidated_on_save` |
| D-5 | N+1 в админке | `list_select_related`, `annotate(Count)` для счётчика, `list_per_page`, `date_hierarchy`, `search_fields` | — |
| D-6 | Модель БД | `rating` → `Decimal(3,2)`, `price` → `Decimal(12,2)`, `MinValueValidator` + `CheckConstraint` (цена ≥ 0, рейтинг 0–5), `updated_at`, `related_name`, `phone`-валидатор | `test_rating_and_price_are_strings_of_exact_decimal` |
| E-1 | Мёртвый код | Удалены `apps/users/views.py`, `apps/users/auth_urls.py`, `data.txt`, корневой `migrations/`; роутер каталога теперь объявлен один раз (`apps/products/urls.py`) | — |
| E-2 | 0 тестов | 59 тестов в `apps/*/tests.py` + `config/test_settings.py` (sqlite in-memory, без внешней БД) | `manage.py test` |
| E-3 | Нет CI/линтеров | `ci.yml` в корне репозитория (активируется `git mv ci.yml .github/workflows/ci.yml`; файл не пушился в `.github/` из-за прав GitHub-приложения) — check, миграции, OpenAPI, тесты, ruff + `ruff.toml` + `requirements/requirements-dev.txt` | CI |
| C-3b | Ошибки не логировались | `LOGGING` (console) + `EXCEPTION_HANDLER`: JSON-ошибки, `IntegrityError`→409, `DatabaseError`→503, лог необработанных исключений с контекстом | `test_404_is_json_not_html` |
| A-7 | `build.sh`-шаг «Суперюзер» ронял прод-сборку (`CommandError: That Email is already taken.`) | Новая идемпотентная команда `ensure_superuser` (поиск `get_by_natural_key` = `iexact`+`strip`; существующий → повышение флагов, пароль **не** трогается без `--update-password`); `build.sh` больше **не** парсит stdout `manage.py shell -c` | `EnsureSuperuserTests` (6 тестов) |

---

## 🚑 Пост-деплой: падение сборки Render

После мержа PR #1 прод-билд упал в самом конце `build.sh`:

```
>>> Суперюзер
CommandError: Error: That Email is already taken.
==> Build failed
```

Всё остальное отработало нормально (Python 3.14, `Django==6.1`, `check` → no issues,
`collectstatic` → «157 copied, 453 post-processed», миграции применились, `seed` пропущен).

### Корень проблемы (воспроизводится 1-в-1)

В `build.sh` был guard:

```bash
EXISTS=$(python manage.py shell -c "…print(User.objects.filter(email=email).exists())")
if [ "$EXISTS" = "True" ]; then … else python manage.py createsuperuser --noinput; fi
```

1. `manage.py shell -c` пишет в stdout **и свою служебную строку**
   (`11 objects imported automatically (use -v 2 for details).` + пустая строка + `True`),
   поэтому `[ "$EXISTS" = "True" ]` не истинно никогда → каждый деплой шёл в `else`.
2. `createsuperuser --noinput` внутри `_validate_username()` бросает
   `CommandError("That Email is already taken")`, а `set -o errexit` роняет весь билд.
3. Вторичная хрупкость: guard сравнивал email точно, а `createsuperuser` — через
   `get_by_natural_key()`, у нас регистронезависимый (`iexact`), т.е. на «наследном»
   `Admin@Example.com` guard тоже промахивается.

### Решение

Новая management-команда `apps/users/management/commands/ensure_superuser.py`
(идемпотентная замена `createsuperuser --noinput`):

* опции `--email --password --first-name --last-name --update-password`, каждая падает
  на env `DJANGO_SUPERUSER_EMAIL / _PASSWORD / _FIRST_NAME / _LAST_NAME / _UPDATE_PASSWORD`;
* `DJANGO_SUPERUSER_EMAIL` пуст → warning и выход с кодом 0 (в деплое это штатно);
* поиск — `User._default_manager.get_by_natural_key(email)` (`iexact` + `strip`, как логин),
  НЕ точное сравнение;
* не найден → `User.objects.create_superuser(...)`; без пароля → `CommandError`;
* найден → ничего не создаём: поднять `is_staff`/`is_superuser`, нормализовать `email`
  к `strip().lower()` (только если нет другой строки с нормализованным email),
  `first/last_name` — если переданы и отличаются; выход всегда код 0;
* **пароль существующего пользователя НЕ трогаем** без `--update-password`
  (иначе каждый деплой возвращает значение из env и отменяет смену пароля в админке);
* `MultipleObjectsReturned` → `CommandError` с объяснением «разберитесь вручную»,
  а не молчаливый выбор пользователя;
* вся логика в `transaction.atomic()`, вывод через `self.style.SUCCESS/WARNING`.

`build.sh` теперь вызывает `python manage.py ensure_superuser` (с `--update-password`,
если `DJANGO_SUPERUSER_UPDATE_PASSWORD=True`) и больше нигде не парсит вывод `manage.py shell -c`.

Живая симуляция шага «Суперюзер» на чистой sqlite-БД (6 состояний, все rc 0, кроме контраста):

| Состояние | Результат | rc |
|---|---|---|
| БД пуста | «Суперюзер создан» | 0 |
| Повторный запуск | «Суперюзер уже в порядке», пароль из env **не** применён (`check_password` старого пароля = True) | 0 |
| В env другой пароль | пароль **не** изменён без `--update-password` | 0 |
| Обычный (не-супер) юзер | «обновлено — is_staff, is_superuser» (+ нормализация email), строк не прибавилось | 0 |
| `DJANGO_SUPERUSER_EMAIL` не задан | пропуск («не задан — суперюзер не создаётся») | 0 |
| Контраст: старая схема `createsuperuser --noinput` | `CommandError: That Email is already taken.` | 1 |

### Не вошло (осознанные follow-up’ы)

| Пункт | Почему отложен |
|---|---|
| `pg_trgm`-индекс + `Unaccent` для fuzzy-поиска (D-2) | требует PostgreSQL: миграция с `CREATE EXTENSION IF NOT EXISTS pg_trgm` + GIN-индекс и проверка на живой БД — на sqlite не прогоняется, поэтому не заводили вслепую; сейчас `search` = `icontains` |
| `parent_id` вместо `parent_id-1` в дереве `Category` (E-4) | меняет контракт; сломает текущих потребителей без отдельного релиза |
| Лимит на `logout` (E-5) | `login`/`register`/`refresh` ограничены и учитывают `X-Forwarded-For`; `logout` не ограничивали — он идемпотентен и не раскрывает данных |
| Sentry/APM, `/api/health/`, метрики Prometheus | внешние сервисы и их ключи; заглушку `/health/` делать смысла нет, она ничего не проверяет (см. D-6) |
| S3/R2 для `media/` | код и зависимости готовы (`USE_S3`), но бакет и ключи должны быть заведены на стороне проекта |
| Password reset (email + токен), e2e-тесты на Playwright | новые фичи/инфраструктура, а не исправления; контракт описан в API.md как «нет» |
| CSP (`Content-Security-Policy`) | базовые заголовки уже стоят на проде (`X-Frame-Options: DENY`, `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY`); полноценный CSP depends on фронтенда (inline-стили у UI-библиотек) и вводить его нужно вместе с ним. `CORS_ALLOWED_ORIGINS`/`CSRF_TRUSTED_ORIGINS` читаются из env — их надо выставить под финальный домен фронта |

### Что изменилось для клиентов (ломать не будет, но знать надо)

1. `POST /auth/register/` больше **не** возвращает `access`/`refresh` в теле — авторизация приходит cookie.
2. `POST /auth/refresh/` возвращает **204** без тела (раньше 200 с пустым телом) и **ротацию**
   refresh-cookie. Тело не обязательно, но если `refresh` в нём передан — он важнее cookie
   (битый токен в теле = `401`, а не «тихий успех» по cookie).
3. `POST /auth/logout/` больше не требует авторизации (401 → 200), реально отзывает refresh.
4. В ответах пагинации добавлены `page_size` и `total_pages`.
5. Список `/products/` отдаёт компактные карточки (`description`, `characteristics`, `images`,
   `seller` — только в деталях); в обоих форматах добавлены `discount_percent`, `created_at`.
6. Неизвестный query-параметр в списке → `400` вместо тихого игнора (отключается правкой
   `LIST_PARAMS`, если нужен прежний looseness).
7. В кросс-доменном режиме (`COOKIE_SAMESITE=None`) unsafe-запросы требуют `X-CSRFToken`
   (бустрап: `GET /api/auth/csrf/`). В same-site/прокси-режиме — не требуют.
8. `rating` теперь строка `"4.95"` (было число `4.95`), `price` — строка (как и раньше).

---

### Приложение: команды, которыми проверялось

```bash
python manage.py check                                  # → 4× (models.W042)
python manage.py makemigrations --check --dry-run       # → хочет 0003_alter_*_id
python manage.py migrate && python manage.py seed
python manage.py spectacular --validate --fail-on-warn  # → Errors: 8, Warnings: 10
curl -i -X POST /api/auth/register/ …                   # → 201, токены в теле, Set-Cookie: нет
curl -i -X POST /api/auth/login/  …                     # → Set-Cookie: SameSite=Lax; Secure
curl -b cookies -X POST /api/auth/refresh/ -H 'Content-Type: application/x-www-form-urlencoded'  # → 500
curl -b 'uzum_access_token=garbage' /api/products/       # → 401 (должно быть 200)
curl -b cookies -X POST /api/auth/logout/ && curl -b cookies -X POST /api/auth/refresh/  # → 200 (токен жив)
curl -k -H 'X-Forwarded-Proto: https' http://…/api/categories/   # → 301 (цикл)
EXPLAIN QUERY PLAN SELECT … ORDER BY created_at DESC LIMIT 10   # → SCAN + TEMP B-TREE
```

---

## Ссылки

* Render, Supported Languages — версия Python задаётся `PYTHON_VERSION` или `.python-version`
  (дефолт меняется, для **ранее созданных** сервисов остаётся прежний):
  <https://render.com/docs/language-support>
* Django 6.x, PostgreSQL notes: psycopg 3 рекомендуется, поддержка psycopg2 «likely to be deprecated»:
  <https://docs.djangoproject.com/en/6.0/ref/databases/>
* MDN, SameSite: `Lax` не отправляется на кросс-сайтовые `fetch/XHR`; установка cookie в ответе на
  кросс-сайтовый запрос требует `SameSite=None; Secure`: <https://developer.mozilla.org/docs/Web/HTTP/Reference/Headers/Set-Cookie/SameSite>
* SimpleJWT, `token_blacklist`: штатный отзыв — `RefreshToken(raw).blacklist()`:
  <https://django-rest-framework-simplejwt.readthedocs.io/en/latest/blacklist_app.html>
