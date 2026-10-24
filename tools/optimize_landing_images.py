"""Prepara las fotos originales de assets/photos/ para la landing.

Uso (desde empacadora-san-juan/):
    .venv\\Scripts\\python.exe tools\\optimize_landing_images.py

Genera static/img/landing/*.webp. Los originales NO se tocan.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "photos"
OUT = ROOT / "static" / "img" / "landing"

BRAND_GREEN = (34, 197, 94)  # verde del logo, un poco mas vivo para fondo oscuro


def save(img: Image.Image, name: str, quality: int = 80) -> None:
    path = OUT / f"{name}.webp"
    img.save(path, "WEBP", quality=quality, method=6)
    print(f"{name:10s} {img.size[0]}x{img.size[1]}  {path.stat().st_size / 1024:6.0f} KB")


def resized(img: Image.Image, width: int) -> Image.Image:
    height = round(img.height * width / img.width)
    return img.resize((width, height), Image.LANCZOS)


def hero() -> None:
    # El original mide 1024 px de ancho: lo duplicamos y afinamos. El grano
    # CSS de la landing disimula el resto, pero lo ideal es regenerarlo en 2K.
    img = Image.open(SRC / "fondo_total.jpg").convert("RGB")
    img = resized(img, 2048).filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=2))
    save(img, "hero", quality=82)


def photo(src: str, name: str, width: int) -> None:
    save(resized(Image.open(SRC / src).convert("RGB"), width), name)


def crate() -> None:
    # Fondo blanco -> transparente: cuanto mas lejos del blanco, mas opaco.
    img = Image.open(SRC / "cesta_verde.jpg.jpg").convert("RGB")
    r, g, b = img.split()
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    alpha = darkest.point(lambda v: max(0, min(255, (255 - v - 10) * 6)))
    img.putalpha(alpha)
    save(img.crop(alpha.getbbox()), "cesta", quality=90)


def logo() -> None:
    # Logo verde sobre negro -> verde sobre transparente (el brillo es el alfa).
    img = Image.open(SRC / "logo_crudo.jpg").convert("RGB")
    r, g, b = img.split()
    brightest = ImageChops.lighter(ImageChops.lighter(r, g), b)
    # Piso de 30: el ruido del JPG alrededor del logo queda 100% transparente.
    alpha = brightest.point(lambda v: max(0, min(255, (v - 30) * 3)))
    solid = Image.new("RGBA", img.size, BRAND_GREEN + (0,))
    solid.putalpha(alpha)
    bbox = alpha.point(lambda v: 255 if v > 40 else 0).getbbox()
    pad = 24
    box = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
    save(solid.crop(box), "logo", quality=95)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    hero()
    photo("volcan_irazu.jpg", "volcan", 2400)
    photo("brocoli.jpg", "brocoli", 1800)
    photo("coliflor.jpg", "coliflor", 1800)
    photo("papa_malla.jpg", "papa", 1800)
    crate()
    logo()
