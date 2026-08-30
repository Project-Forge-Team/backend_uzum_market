"""Демо-картинки сида: /products/gen/<name>.svg + их генерация (§9 ТЗ).

Сид генерирует простые SVG-плейсхолдеры в seed_media/products/gen/. Фронтенд
имеет собственные копии этих файлов в public/ — отдача с бэкенда нужна для
прямого обращения к API (e2e, превью) и как фолбэк.
"""

from django.conf import settings
from django.http import FileResponse, Http404
from django.views import View

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{c1}"/>
      <stop offset="1" stop-color="{c2}"/>
    </linearGradient>
  </defs>
  <rect width="600" height="600" fill="url(#g)"/>
  <circle cx="470" cy="130" r="90" fill="rgba(255,255,255,0.18)"/>
  <circle cx="120" cy="480" r="130" fill="rgba(255,255,255,0.12)"/>
  <text x="300" y="290" font-size="140" text-anchor="middle">{emoji}</text>
  <text x="300" y="400" font-size="30" text-anchor="middle" fill="rgba(20,20,31,0.75)"
        font-family="Arial, sans-serif" font-weight="600">{label}</text>
</svg>
"""

PALETTE = [
    ("#EDE9FF", "#D6CFFF"),
    ("#FFE8D6", "#FFD3B6"),
    ("#DFF2FF", "#BFE3FF"),
    ("#E3F6E8", "#C6EED4"),
    ("#FFE3EC", "#FFC9DD"),
    ("#FFF6D6", "#FFEBAD"),
    ("#E8E9FF", "#CFD1FF"),
    ("#E4F6FF", "#C2EDFF"),
]


def svg_for(name: str, emoji: str, label: str, index: int) -> str:
    c1, c2 = PALETTE[index % len(PALETTE)]
    return SVG_TEMPLATE.format(c1=c1, c2=c2, emoji=emoji, label=label[:30])


def write_svg(rel_name: str, emoji: str, label: str, index: int) -> None:
    target_dir = settings.SEED_MEDIA_ROOT / "products" / "gen"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / rel_name).write_text(svg_for(rel_name, emoji, label, index), encoding="utf-8")


class SeedMediaView(View):
    """GET /products/gen/<name>.svg — раздача демо-картинок с долгим кэшем."""

    def get(self, request, name: str):
        if "/" in name or ".." in name or not name.endswith(".svg"):
            raise Http404("Файл не найден.")
        path = settings.SEED_MEDIA_ROOT / "products" / "gen" / name
        if not path.is_file():
            raise Http404("Файл не найден.")
        response = FileResponse(path.open("rb"), content_type="image/svg+xml")
        response["Cache-Control"] = "public, max-age=86400"
        return response
