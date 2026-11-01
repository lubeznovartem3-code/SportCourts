"""Безопасная обработка загружаемых изображений (только Pillow, без веб-слоя).

Конвейер: проверка размера → проверка реального формата по содержимому →
защита от «бомб» распаковки → поворот по EXIF → удаление метаданных →
ограничение разрешения → сохранение в JPEG. Оригинал не сохраняется.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageError(Exception):
    """Ошибка обработки изображения; code и message безопасно показывать пользователю."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ImageLimits:
    max_bytes: int
    max_dimension: int
    max_pixels: int
    jpeg_quality: int


def process_image(data: bytes, limits: ImageLimits) -> bytes:
    """Возвращает готовый JPEG. Бросает ImageError с понятным сообщением."""
    if not data:
        raise ImageError("empty_file", "Файл пустой")
    if len(data) > limits.max_bytes:
        mb = limits.max_bytes / (1024 * 1024)
        raise ImageError("file_too_large", f"Файл слишком большой (максимум {mb:g} МБ)", 413)

    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        width, height = probe.size
        probe.verify()  # проверяет целостность, не декодируя пиксели полностью
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ImageError("invalid_image", "Файл не является поддерживаемым изображением (JPEG, PNG или WebP)")

    if fmt not in ALLOWED_FORMATS:
        raise ImageError("unsupported_format", "Поддерживаются только JPEG, PNG и WebP")
    if width < 1 or height < 1 or width * height > limits.max_pixels:
        raise ImageError("image_too_large", "Разрешение изображения слишком велико")

    try:
        img = Image.open(io.BytesIO(data))  # после verify() объект непригоден — открываем заново
        img.load()
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            img = background
        else:
            img = img.convert("RGB")
        img.thumbnail((limits.max_dimension, limits.max_dimension), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        # exif и прочие метаданные не передаются — они не попадут в сохранённый файл
        img.save(out, format="JPEG", quality=limits.jpeg_quality, optimize=True)
        return out.getvalue()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ImageError("invalid_image", "Не удалось обработать изображение")
