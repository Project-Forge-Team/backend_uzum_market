#!/usr/bin/env python3
"""E2E-проверка контракта Uzum Market Clone — 55 проверок против живого сервера.

Использование:
    UZUM_BASE_URL=https://backend.example.com python3 scripts/e2e.py
    python3 scripts/e2e.py http://127.0.0.1:8000

Только стандартная библиотека — запускайте где угодно. Внимание: скрипт делает ~8 POST
на auth-эндпоинты, а лимит — 10/мин с одного IP, поэтому не запускайте его чаще раза в минуту.
Скрипт самонастраивается:
регистрирует временных пользователей, создаёт магазин и товар, оформляет заказ,
пишет отзыв — и в конце возвращает БД к сид-состоянию через POST /api/demo/reset/.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("UZUM_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
PASSWORD = "Password123"  # noqa: S105 — демо-пароль из ТЗ (§9)

PNG_1x1 = (
    b"\x89PNG\r\n\x1a\n"
    + (lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d)))(
        b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    )
    + (lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d)))(
        b"IDAT", zlib.compress(b"\x00\xff\x00\x00")
    )
    + (lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d)))(b"IEND", b"")
)

PASSED = FAILED = 0
_n = 0


def check(ok, label, extra=""):
    global PASSED, FAILED, _n
    _n += 1
    print(("✓" if ok else "✗") + f" [{_n:02d}/55] {label}" + (f"  —  {extra}" if extra and not ok else ""))
    PASSED, FAILED = PASSED + (1 if ok else 0), FAILED + (0 if ok else 1)


class Resp:
    def __init__(self, code, body, headers):
        self.status_code, self.text, self.headers = code, body.decode("utf-8", "replace"), headers

    def json(self):
        try:
            return json.loads(self.text)
        except ValueError:
            return {}


class Client:
    """HTTP-клиент на cookiejar с автоматическим CSRF-заголовком."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def token(self):
        return next((c.value for c in self.jar if c.name == "uzum_csrf"), "")

    def csrf(self):
        self.get("/api/auth/csrf/")
        return self.token()

    def request(self, method, path, data=None, headers=None, raw=None, ctype="application/json"):
        h = {"Accept": "application/json"}
        if data is not None:
            h["Content-Type"] = ctype
            raw = json.dumps(data, ensure_ascii=False).encode()
        h.update(headers or {})
        path = urllib.parse.quote(path, safe="/?&=%+,:@$")
        req = urllib.request.Request(BASE + path, data=raw, headers=h, method=method)  # noqa: S310
        try:
            r = self.opener.open(req, timeout=20)
            return Resp(r.status, r.read(), r.headers)
        except urllib.error.HTTPError as e:
            return Resp(e.code, e.read(), e.headers)

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, data=None, headers=None):
        return self.request("POST", path, data, {"X-CSRFToken": self.token(), **(headers or {})})

    def put(self, path, data=None):
        return self.request("PUT", path, data, {"X-CSRFToken": self.token()})

    def patch(self, path, data=None):
        return self.request("PATCH", path, data, {"X-CSRFToken": self.token()})

    def delete(self, path):
        return self.request("DELETE", path, None, {"X-CSRFToken": self.token()})

    def upload(self, name="shot.png", content_type="image/png", content=None):
        body = content if content is not None else PNG_1x1
        boundary = uuid.uuid4().hex
        raw = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + body
            + f"\r\n--{boundary}--\r\n".encode()
        )
        return self.request(
            "POST",
            "/api/uploads/",
            None,
            {"X-CSRFToken": self.token(), "Content-Type": f"multipart/form-data; boundary={boundary}"},
            raw=raw,
        )

    def login(self, email, password=PASSWORD):
        r = self.post("/api/auth/login/", {"email": email, "password": password})
        if r.status_code == 429:  # лимит 10/мин с IP (§4 ТЗ) — подождём и повторим раз
            m = re.search(r"available in (\d+) seconds", r.text)
            wait = int(m.group(1)) + 1 if m else 61
            print(f"    … login-троттлинг, ждём {wait} c и повторяем")
            time.sleep(wait)
            r = self.post("/api/auth/login/", {"email": email, "password": password})
        return r


def main():
    anon = Client()
    anon.csrf()
    stamp = str(int(time.time()))[-8:]

    # ——— Здоровье и каталог ———
    r = anon.get("/api/health")
    h = r.json()
    check(
        r.status_code == 200
        and h.get("status") == "ok"
        and h.get("service") == "uzum-market-clone"
        and isinstance(h.get("products"), int)
        and h.get("time", "").endswith("Z"),
        "GET /health: статус/сервис/счётчик/время",
        r.text[:120],
    )

    r = anon.get("/api/categories/")
    c = r.json()
    check(
        r.status_code == 200
        and c.get("count") == 10
        and c.get("total_pages") == 1
        and c.get("next") is False
        and c.get("previous") is False,
        "GET /categories/: конверт, count=10",
        r.text[:150],
    )

    ok = all({"id", "name", "slug", "emoji", "color", "product_count"} <= set(x) for x in c["results"])
    check(
        ok and all(isinstance(x["product_count"], int) for x in c["results"]), "GET /categories/: поля и product_count"
    )

    r = anon.get("/api/sellers/")
    s = r.json()
    ratings = [x["rating"] for x in s["results"]]
    check(
        r.status_code == 200 and ratings == sorted(ratings, reverse=True),
        "GET /sellers/: конверт и сортировка по рейтингу ↓",
    )

    first = s["results"][0]
    d = anon.get(f"/api/sellers/{first['id']}/").json()
    check(
        d.get("id") == first["id"] and isinstance(d.get("products"), list),
        "GET /sellers/{id}/: профиль + активные товары",
    )

    check(
        anon.get(f"/api/sellers/{first['slug']}/").json().get("id") == first["id"],
        "GET /sellers/{slug}/: тот же магазин",
    )

    p = anon.get("/api/products/").json()
    check(
        p.get("count") == 42
        and p.get("page_size") == 20
        and p.get("total_pages") == 3
        and len(p.get("results", [])) == 20,
        "GET /products/: конверт (count=42, page_size=20, total_pages=3)",
        json.dumps(p)[:150],
    )

    r1 = anon.get("/api/products/?page_size=1000").json()
    r2 = anon.get("/api/products/?page_size=1").json()
    check(len(r1["results"]) == 42 and r1["page_size"] == 120 and r2["page_size"] == 4, "page_size: клампится в 4..120")

    f = p.get("facets", {})
    check(
        isinstance(f.get("price", {}).get("min"), int)
        and isinstance(f.get("price", {}).get("max"), int)
        and len(f.get("categories", [])) > 0,
        "GET /products/: facets.price и facets.categories",
    )

    card = p["results"][0]
    need = {
        "slug",
        "discount_percent",
        "monthly_payment",
        "rating_breakdown",
        "brand",
        "views",
        "status",
        "seller",
        "category",
        "in_stock",
        "old_price",
    }
    mp = card.get("monthly_payment", {})
    check(
        need <= set(card) and mp.get("months") == 12 and "per_month" in mp,
        "карточка товара: обязательные вычисляемые поля",
    )

    r = anon.get("/api/products/?discounted=1").json()
    ok = all(x["old_price"] and x["old_price"] > x["price"] and x["discount_percent"] > 0 for x in r["results"])
    check(r["count"] > 0 and ok, "discounted=1: у всех old_price>price и скидка>0")

    r = anon.get("/api/products/?q=самокат").json()
    r2b = anon.get("/api/products/?search=самокат").json()
    check(
        r["count"] > 0 and r["count"] == r2b["count"] and all("самокат" in x["title"].lower() for x in r["results"]),
        "q= и search= ищут по названию",
    )

    r = anon.get("/api/products/?max_price=200000").json()
    check(
        all(x["price"] <= 200000 for x in r["results"])
        and anon.get("/api/products/?min_price=5000000").json()["count"] > 0,
        "min_price/max_price: границы включительно",
    )

    r = anon.get("/api/products/?in_stock=1").json()
    check(all(x["in_stock"] for x in r["results"]), "in_stock=1: только товары в наличии")

    prices = [x["price"] for x in anon.get("/api/products/?ordering=price").json()["results"]]
    check(prices == sorted(prices), "ordering=price: по возрастанию")

    sample = p["results"][0]["id"]
    r = anon.get(f"/api/products/?ids={sample}&in_stock=0&max_price=1").json()
    check(r["count"] == 1 and r["results"][0]["id"] == sample, "ids= перекрывает прочие фильтры")

    check(
        anon.get("/api/products/?status=draft").json()["count"] == 0,
        "status=draft анониму: count=0 (чужие черновики скрыты)",
    )

    by_id = anon.get(f"/api/products/{sample}/").json()
    by_slug = anon.get(f"/api/products/{by_id['slug']}/").json()
    check(by_id["id"] == by_slug["id"] and by_id["title"] == by_slug["title"], "товар по id и по slug — одно и то же")

    v0 = by_id["views"]
    check(
        anon.post(f"/api/products/{sample}/view/").json().get("ok") is True
        and anon.get(f"/api/products/{sample}/").json()["views"] == v0 + 1,
        "POST /view/: инкремент просмотров без авторизации",
    )

    # ——— Авторизация ———
    check(anon.get("/api/auth/me/").status_code == 401, "аноним /auth/me/ → 401 (не 500/403)")

    check(anon.post("/api/orders/", {"items": []}).status_code == 401, "аноним POST /orders/ (с CSRF) → 401")

    raw = Client()
    check(
        raw.request("POST", "/api/auth/register/", {"email": "x@y.z"}).status_code == 403, "POST без X-CSRFToken → 403"
    )

    buyer2 = Client()
    buyer2.csrf()
    r = buyer2.post(
        "/api/auth/register/",
        {
            "email": f"e2e_{stamp}@test.uz",
            "password": "Str0ngPass!123",
            "password2": "Str0ngPass!123",
            "first_name": "Э2Э",
            "last_name": "Покупатель",
        },
    )
    b = r.json()
    check(
        r.status_code == 201
        and b.get("email") == f"e2e_{stamp}@test.uz"
        and b.get("is_seller") is True
        and isinstance(b.get("seller_id"), int),
        "регистрация: 201 + вход сразу + автоматический магазин (§0.1 ТЗ)",
        r.text[:150],
    )

    demo_buyer = Client()
    demo_buyer.csrf()
    r = demo_buyer.login("buyer@uzum.uz")
    check(r.status_code == 200 and r.json().get("email") == "buyer@uzum.uz", "логин демо-покупателя")

    bad = Client()
    bad.csrf()
    check(bad.login("buyer@uzum.uz", "wrong").status_code == 401, "неверный пароль → 401")

    r = demo_buyer.patch("/api/auth/me/", {"first_name": "Азиз"})
    me = demo_buyer.get("/api/auth/me/").json()
    check(r.status_code == 200 and me.get("first_name") == "Азиз", "PATCH /auth/me/: частичное обновление")

    check(any(c.name == "uzum_sessionid" for c in demo_buyer.jar), "логин ставит куку uzum_sessionid")

    r = buyer2.post("/api/auth/password/", {"current": "Str0ngPass!123", "next": "N3wStr0ngPass!9"})
    relogin = Client()
    relogin.csrf()
    ok = r.status_code == 200 and relogin.login(f"e2e_{stamp}@test.uz", "N3wStr0ngPass!9").status_code == 200
    check(ok, "смена пароля: 200, вход по новому паролю", r.text[:120])

    # ——— Магазин ———
    seller = Client()
    seller.csrf()
    seller.post(
        "/api/auth/register/",
        {
            "email": f"e2e_shop_{stamp}@test.uz",
            "password": "Str0ngPass!123",
            "password2": "Str0ngPass!123",
            "first_name": "Э2Э",
            "last_name": "Продавец",
        },
    )
    r = demo_buyer.get("/api/shop/")
    check(r.status_code == 200 and r.json() is None, "GET /shop/ у покупателя без магазина → 200 null", r.text[:80])

    have = seller.get("/api/shop/").json()
    r1 = seller.post("/api/shop/", {"name": have["name"], "description": have.get("description") or ""})
    r2s = seller.post("/api/shop/", {"name": have["name"], "description": have.get("description") or ""})
    check(
        r1.status_code == 200 and r2s.status_code == 200 and r1.json().get("id") == have["id"] == r2s.json().get("id"),
        "POST /shop/ повторно: идемпотентный 200 с тем же id (не 409, не дубль)",
        f"{r1.status_code}/{r2s.status_code}",
    )

    # ——— CRUD товара ———
    r = seller.post(
        "/api/products/",
        {
            "title": f"Проверка скрипта {stamp}",
            "description": "Описание длиннее двадцати символов для скрипта.",
            "price": 250_000,
            "old_price": 300_000,
            "stock": 5,
            "category_id": c["results"][0]["id"],
            "delivery_time": "Завтра",
            "brand": "E2E",
        },
    )
    prod = r.json()
    created = seller.get(f"/api/products/{prod['id']}/").json() if r.status_code == 201 else {}
    check(
        r.status_code == 201
        and prod.get("detail") == "Товар опубликован"
        and created.get("slug", "").startswith("proverka-skripta")
        and created.get("discount_percent") == 17,
        "POST /products/: 201, слаг транслит, скидка ≈17%",
        r.text[:180],
    )

    mine = seller.get("/api/products/mine/").json()
    check(any(x["id"] == prod["id"] for x in mine.get("results", [])), "GET /products/mine/: свой товар")

    r = seller.patch(f"/api/products/{prod['id']}/", {"title": "коротк"})
    r2p = seller.patch(f"/api/products/{prod['id']}/", {"price": 260_000})
    again = seller.get(f"/api/products/{prod['id']}/").json()
    check(
        r.status_code == 400
        and "title" in r.json().get("fields", {})
        and r2p.status_code == 200
        and again["title"].startswith("Проверка")
        and again["price"] == 260_000,
        "PATCH: merge-валидация (400 по полю) и частичное обновление",
        f"{r.status_code}/{r2p.status_code}",
    )

    r = seller.post(f"/api/products/{prod['id']}/status/", {"status": "draft"})
    r2st = seller.post(f"/api/products/{prod['id']}/status/", {"status": "draft"})
    check(
        r.status_code == 200
        and r2st.status_code == 200
        and seller.get(f"/api/products/{prod['id']}/").json().get("status") == "draft",
        "POST /status/: черновик, идемпотентен",
    )

    drafts = seller.get("/api/products/?status=draft").json()
    check(
        any(x["id"] == prod["id"] for x in drafts["results"])
        and anon.get(f"/api/products/{prod['id']}/").status_code == 404,
        "чужой черновик: владельцу виден, анониму 404",
    )

    seller.post(f"/api/products/{prod['id']}/status/", {"status": "active"})

    electro = Client()
    electro.csrf()
    electro.login("electro@uzum.uz")
    electro_prod = electro.get("/api/products/mine/").json()["results"][0]["id"]
    r = demo_buyer.patch(f"/api/products/{electro_prod}/", {"price": 1})
    check(r.status_code == 403, "чужой PATCH чужого товара → 403", str(r.status_code))

    # ——— Отзывы ———
    r = anon.get(f"/api/products/{prod['id']}/reviews/")
    sm = r.json().get("summary", {})
    stars = [row.get("stars") for row in sm.get("breakdown", [])]
    check(
        r.status_code == 200 and stars == [5, 4, 3, 2, 1] and "average" in sm and "count" in sm,
        "GET reviews: summary.count/average/breakdown 5→1",
        r.text[:160],
    )

    check(
        anon.post(
            f"/api/products/{prod['id']}/reviews/", {"rating": 5, "text": "Аноним не может оставлять отзывы"}
        ).status_code
        == 401,
        "аноним POST review → 401",
    )

    r = buyer2.post(f"/api/products/{prod['id']}/reviews/", {"rating": 5, "text": "Отличный товар, всё пришло!"})
    check(
        r.status_code == 403 and "купили этот товар" in r.json().get("detail", ""),
        "без покупки → 403 «могут оставить только покупатели»",
        r.text[:160],
    )

    r = buyer2.post(
        "/api/orders/",
        {
            "items": [{"product_id": prod["id"], "qty": 1}],
            "delivery_method": "pickup",
            "payment_method": "cash",
            "pickup_point": "ПВЗ e2e",
            "buyer_name": "Э2Э Покупатель",
        },
    )
    order = r.json()
    full = buyer2.get(f"/api/orders/{order.get('id', 0)}/").json() if r.status_code == 201 else {}
    check(
        r.status_code == 201
        and re.fullmatch(r"UZ-\d{6}", full.get("number", ""))
        and full.get("subtotal") == 260_000
        and full.get("total") == 260_000
        and full.get("items", [{}])[0].get("price") == 260_000,
        "POST /orders/: 201, номер UZ-XXXXXX, суммы с сервера",
        r.text[:220],
    )

    r1 = buyer2.post(
        f"/api/products/{prod['id']}/reviews/", {"rating": 5, "text": "Отличный товар, всё пришло вовремя!"}
    )
    r2r = buyer2.post(
        f"/api/products/{prod['id']}/reviews/", {"rating": 4, "text": "Хороший товар, доставка супер быстро!"}
    )
    a, b2 = r1.json(), r2r.json()
    check(
        r1.status_code == 201 and r2r.status_code == 200 and a.get("id") == b2.get("id") and b2.get("updated") is True,
        "POST review: upsert (201 → 200 updated=true, тот же id)",
        f"{r1.status_code}/{r2r.status_code}",
    )

    r = seller.post(f"/api/reviews/{a['id']}/reply/", {"reply": "Спасибо за отзыв, приходите ещё!"})
    reply_seen = buyer2.get(f"/api/products/{prod['id']}/reviews/").json()["results"][0].get("seller_reply")
    check(
        r.status_code == 200 and reply_seen == "Спасибо за отзыв, приходите ещё!",
        "POST /reviews/{id}/reply/: ответ продавца виден покупателю",
        r.text[:120],
    )

    r = buyer2.delete(f"/api/reviews/{a['id']}/")
    sm2 = buyer2.get(f"/api/products/{prod['id']}/reviews/").json()["summary"]
    check(r.status_code == 200 and sm2["count"] == sm["count"], "DELETE своего отзыва → 200, агрегаты пересчитаны")

    # ——— Превью и границы заказов ———
    d = anon.put("/api/orders/", {"subtotal": 400_000, "delivery_method": "courier"}).json()
    check(
        d.get("delivery_cost") == 25_000 and d.get("total") == 425_000,
        "PUT превью: без CSRF, доставка 25 000 (<500k)",
        json.dumps(d, ensure_ascii=False),
    )

    d = anon.put("/api/orders/", {"subtotal": 600_000, "delivery_method": "courier", "promo_code": "uzum2026"}).json()
    check(
        d.get("discount") == 30_000 and d.get("promo_valid") is True and d.get("delivery_cost") == 0,
        "PUT превью: промокод UZUM2026 −5% и бесплатная доставка",
        json.dumps(d, ensure_ascii=False),
    )

    r = buyer2.post(
        "/api/orders/",
        {
            "items": [{"product_id": prod["id"], "qty": 10}],
            "delivery_method": "pickup",
            "payment_method": "cash",
            "pickup_point": "ПВЗ",
        },
    )
    body = r.json()
    check(
        r.status_code == 400 and "на складе всего" in str(body.get("fields", {}).get("items", body.get("detail", ""))),
        "недостаток остатка → 400 «на складе всего N шт.»",
        r.text[:160],
    )

    lst = buyer2.get("/api/orders/").json()
    check(
        any(o["id"] == order["id"] for o in lst.get("results", [])) and lst.get("total_pages") == 1,
        "GET /orders/: конверт со своим заказом",
    )

    r = seller.get(f"/api/orders/{order['id']}/")
    check(r.status_code == 200 and r.json().get("id") == order["id"], "продавец позиции видит заказ")

    check(electro.get(f"/api/orders/{order['id']}/").status_code == 404, "чужой заказ → 404")

    r = seller.post(f"/api/orders/{order['id']}/status/", {"action": "advance"})
    full2 = seller.get(f"/api/orders/{order['id']}/").json()
    check(
        r.status_code == 200
        and full2.get("status") == "packing"
        and [e["status"] for e in full2.get("timeline", [])][:2] == ["new", "packing"],
        "advance продавцом: new→packing + таймлайн",
        r.text[:160],
    )

    stock_before = seller.get(f"/api/products/{prod['id']}/").json()["stock"]
    r = buyer2.post(f"/api/orders/{order['id']}/status/", {"action": "cancel"})
    stock_after = seller.get(f"/api/products/{prod['id']}/").json()["stock"]
    cancelled = buyer2.get(f"/api/orders/{order['id']}/").json().get("status")
    check(
        r.status_code == 200 and cancelled == "cancelled" and stock_after == stock_before + 1,
        "cancel покупателем: статус + возврат остатка",
        f"{r.status_code} {stock_before}->{stock_after}",
    )

    r = seller.get("/api/shop/orders/")
    so = r.json()
    stats = so.get("stats", {})
    need = {"product_count", "draft_count", "review_count", "rating", "views", "order_count", "revenue", "stock_units"}
    check(
        r.status_code == 200
        and need <= set(stats)
        and any(o["id"] == order["id"] for o in so.get("results", []))
        and stats.get("revenue") == 0,
        "GET /shop/orders/: статистика продавца, revenue после отмены = 0",
        json.dumps(stats)[:180],
    )

    # ——— Загрузки ———
    r = seller.upload()
    u = r.json()
    got = anon.get(u.get("url", "/api/uploads/__none__"))
    check(
        r.status_code == 201
        and u.get("url", "").startswith("/api/uploads/")
        and got.status_code == 200
        and "immutable" in got.headers.get("Cache-Control", ""),
        "POST /uploads/: 201 + отдача immutable",
        r.text[:140],
    )

    check(
        seller.upload(name="note.txt", content_type="text/plain", content=b"hello").status_code == 400,
        "POST /uploads/ не-картинка → 400",
    )

    # ——— Демо-сброс ———
    r = demo_buyer.post("/api/demo/reset/")
    ok = r.status_code == 200 and anon.get("/api/categories/").json()["count"] == 10
    check(ok, "POST /demo/reset/: восстановление сида", r.text[:140])

    print(f"\nИтог: {PASSED}/55 прошло, {FAILED} упало.")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
