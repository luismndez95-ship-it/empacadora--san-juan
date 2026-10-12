"""Logica de negocio del seguimiento de producto empacado: resumen diario
por producto, eficiencia real vs meta. Paralelo a payroll.py pero para
cantidades en vez de horas/dinero.
"""
from __future__ import annotations

from datetime import date, timedelta

# Mapeo simple nombre-de-producto -> archivo de foto en assets/photos/.
# Coincidencia por substring, sin acentos, para que "Brocoli Tipo A" o
# "Coliflor Florete Blanco" encuentren su foto sin que el admin tenga
# que escribir el nombre exacto del archivo. Si el producto no hace
# match con nada de esta lista (o la foto simplemente no existe todavia
# en el servidor), la tarjeta usa la insignia con inicial como respaldo
# -- ver el atributo onerror en admin_dashboard.html.
PRODUCT_PHOTO_MAP = {
    "brocoli": "brocoli.jpg",
    "coliflor": "coliflor.jpg",
    "papa": "papa_malla.jpg",
}

_ACCENTS = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")


def match_product_photo(product_name: str) -> str | None:
    """Devuelve el nombre de archivo de foto que probablemente le
    corresponde a este producto, o None si no reconocemos el cultivo."""
    normalized = product_name.translate(_ACCENTS).lower()
    for keyword, filename in PRODUCT_PHOTO_MAP.items():
        if keyword in normalized:
            return filename
    return None


def build_daily_summary(entries: list[dict], products: list[dict]) -> dict:
    """Agrupa los registros de un dia por producto y calcula eficiencia
    contra la meta diaria de cajas (si el producto tiene una definida).

    `entries` viene de db.get_packing_entries_for_date (incluye product_name
    y daily_target_boxes ya unidos). `products` es la lista completa de
    productos activos, para que los que no tuvieron registro hoy tambien
    aparezcan en cero -- asi el supervisor ve de un vistazo que falta
    capturar algo.
    """
    by_product: dict[int, dict] = {}
    for p in products:
        if not p["active"]:
            continue
        by_product[p["id"]] = {
            "product_id": p["id"],
            "product_name": p["name"],
            "target_boxes": p["daily_target_boxes"],
            "description": p.get("description"),
            "unit_label": p.get("unit_label") or "Cajas",
            "boxes": 0.0,
            "kg": 0.0,
            "entry_ids": [],
        }

    for e in entries:
        row = by_product.setdefault(e["product_id"], {
            "product_id": e["product_id"],
            "product_name": e["product_name"],
            "target_boxes": e["daily_target_boxes"],
            "description": e.get("description"),
            "unit_label": e.get("unit_label") or "Cajas",
            "boxes": 0.0,
            "kg": 0.0,
            "entry_ids": [],
        })
        row["boxes"] += e["boxes"]
        row["kg"] += e["kg"]
        row["entry_ids"].append(e["id"])

    rows = sorted(by_product.values(), key=lambda r: r["product_name"])
    for row in rows:
        target = row["target_boxes"]
        row["efficiency_pct"] = round((row["boxes"] / target) * 100, 1) if target else None
        row["photo_filename"] = match_product_photo(row["product_name"])

    total_boxes = sum(r["boxes"] for r in rows)
    total_kg = sum(r["kg"] for r in rows)
    total_target = sum(r["target_boxes"] for r in rows if r["target_boxes"])
    overall_efficiency = round((total_boxes / total_target) * 100, 1) if total_target else None

    return {
        "rows": rows,
        "total_boxes": total_boxes,
        "total_kg": total_kg,
        "overall_efficiency": overall_efficiency,
    }


def shift_date(d: date, days: int) -> str:
    return (d + timedelta(days=days)).isoformat()
