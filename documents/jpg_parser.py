# jpg_parser.py
import os
import re
import io
import json
import logging
import unicodedata
from typing import Dict, Tuple, Optional

from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

# ---------------------
# ВАЛИДАЦИЯ ИИН + ДАТЫ
# ---------------------

RE_IIN = re.compile(r'(?<!\d)(\d{12})(?!\d)')
RE_DATE = re.compile(r'(\d{1,2})[./](\d{1,2})[./](\d{2,4})')

def validate_iin(iin: str) -> bool:
    if not re.fullmatch(r'\d{12}', iin):
        return False
    digits = [int(d) for d in iin]
    s = sum(digits[i] * (i + 1) for i in range(11)) % 11
    if s == 10:
        s = sum(digits[i] * (i + 3) for i in range(11)) % 11
    return s == digits[11]

def normalize_date(s: str) -> str:
    m = RE_DATE.search(s)
    if not m:
        return ""
    d, mth, y = m.groups()
    d = int(d); mth = int(mth); y = int(y)
    if y < 100:  # 24 -> 2024 (эвристика)
        y += 2000 if y < 50 else 1900
    if 1 <= d <= 31 and 1 <= mth <= 12 and 1900 <= y <= 2100:
        return f"{d:02d}.{mth:02d}.{y}"
    return ""

# ---------------------
# ВСПОМОГАТЕЛЬНОЕ
# ---------------------

def _normalize_unicode(s: str) -> str:
    """Нормализация юникода, чтобы буквы с диакритикой были в NFC."""
    return unicodedata.normalize("NFC", s) if s else s

def _titlecase_cyr(s: str) -> str:
    """
    Преобразует 'ӘБДІ-ҚАДЫР' -> 'Әбді-Қадыр', сохраняя дефисы/апострофы.
    Работает и для латиницы.
    """
    if not s:
        return s
    parts = []
    # разделяем, сохраняя разделители в результате
    for tok in re.split(r"([-ʼ'’])", s):
        if tok and tok not in "-ʼ'’":
            parts.append(tok[:1] + tok[1:].lower())
        else:
            parts.append(tok)
    return "".join(parts)

# ---------------------
# ОСНОВНОЙ ПАРСЕР ROI
# ---------------------

class JPGCoordinateParser:
    """
    Извлекаем ТОЛЬКО текстовые: last_name, first_name, patronymic, iin
    + фото по ROI (photo)
    """
    def __init__(
        self,
        lang_text: str = "kaz+rus",
        lang_digits: str = "eng",
        default_psm: int = 7,
    ):
        self.lang_text = lang_text
        self.lang_digits = lang_digits
        self.default_psm = default_psm

        # Разделяем наборы: текстовые поля и полный набор (включая фото)
        self.allowed_text_fields = {"last_name", "first_name", "patronymic", "iin"}
        self.allowed_all_fields  = set(self.allowed_text_fields) | {"photo"}

        self.coordinates = self.load_coordinates()

        # PSM под поля (7 — одна строка)
        self.psm_by_field = {
            "iin": 7,
            "last_name": 7,
            "first_name": 7,
            "patronymic": 7,
        }

        # Вайтлист только для цифр ИИН
        self.whitelist_by_field = {
            "iin": "0123456789",
        }

        # Служебные слова, которые надо убрать из ФИО (в верхнем регистре)
        self.bad_labels = {"ТЕГІ", "ФАМИЛИЯ", "АТЫ", "ИМЯ", "ӘКЕСІНІҢ", "ОТЧЕСТВО"}

        # Разрешённые символы: латиница A-Z, расширенная кириллица \u0400-\u052F, дефис и апострофы
        self.name_keep_re = re.compile(r"[^A-Z\u0400-\u052F\-ʼ'’]")

    def load_coordinates(self) -> Dict[str, Tuple[float, float, float, float]]:
        """
        Загружаем координаты, оставляем только нужные ключи (в т.ч. photo).
        """
        data = {}
        try:
            coords_file = os.path.join(settings.BASE_DIR, "coordinate_config.json")
            if os.path.exists(coords_file):
                with open(coords_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for k, v in list(raw.items()):
                    if k in self.allowed_all_fields and isinstance(v, (list, tuple)) and len(v) == 4:
                        data[k] = v
        except Exception:
            logger.exception("Failed to load coordinate_config.json")

        if data:
            return data

        # дефолты (добавлено photo)
        return {
            "last_name":   [0.389, 0.190, 0.873, 0.225],
            "first_name":  [0.388, 0.243, 0.874, 0.278],
            "patronymic":  [0.390, 0.304, 0.885, 0.328],
            "iin":         [0.183, 0.407, 0.404, 0.438],
            "photo":       [0.105, 0.163, 0.357, 0.391],
        }

    def extract_data_from_jpg(self, jpg_path: str) -> Dict:
        result = {
            "first_name": "", "last_name": "", "patronymic": "", "iin": "",
            "photo": None,
            "debug_info": {}
        }

        try:
            image = Image.open(jpg_path)
            width, height = image.size

            # Текстовые поля
            for field, coords in self.coordinates.items():
                if field not in self.allowed_text_fields:
                    continue

                l, t, r, b = self._to_pixels(coords, width, height)
                if not self._is_valid_box(l, t, r, b, width, height):
                    logger.warning("Invalid ROI %s: %s", field, coords)
                    continue

                roi = image.crop((l, t, r, b))
                enhanced = self._enhance_for_ocr(roi, field)
                text = self._ocr(enhanced, field)
                cleaned = self._clean(field, text)

                result[field] = cleaned
                result["debug_info"][field] = {"bbox": [l, t, r, b], "raw": text}

            # Фото
            if "photo" in self.coordinates:
                photo_file = self._extract_photo(image)
                if photo_file:
                    result["photo"] = photo_file
                    # для дебага положим bbox
                    l, t, r, b = self._to_pixels(self.coordinates["photo"], width, height)
                    result["debug_info"]["photo"] = {"bbox": [l, t, r, b]}

            # финальная валидация ИИН
            if result["iin"] and not validate_iin(result["iin"]):
                result["debug_info"].setdefault("warnings", []).append("IIN checksum failed")

        except Exception:
            logger.exception("extract_data_from_jpg failed for %s", jpg_path)

        return result

    # --- помощьники ---

    @staticmethod
    def _to_pixels(coords, w, h):
        left = int(coords[0] * w)
        top = int(coords[1] * h)
        right = int(coords[2] * w)
        bottom = int(coords[3] * h)
        return left, top, right, bottom

    @staticmethod
    def _is_valid_box(l, t, r, b, W, H):
        return 0 <= l < r <= W and 0 <= t < b <= H

    def _enhance_for_ocr(self, img: Image.Image, field: str) -> Image.Image:
        """
        Лёгкая предобработка:
        - градации серого
        - автоконтраст
        - немного контраста/резкости
        - апскейл при мелких ROI (особенно для числовых полей)
        """
        try:
            if img.mode != "L":
                img = img.convert("L")

            img = ImageOps.autocontrast(img)
            img = ImageEnhance.Contrast(img).enhance(1.6)
            img = ImageEnhance.Sharpness(img).enhance(1.3)

            min_side = min(img.size)
            if min_side < 40:
                scale = 2.0
            elif min_side < 80:
                scale = 1.5
            else:
                scale = 1.2 if field in ("iin",) else 1.0

            if scale > 1.0:
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            return img
        except Exception as e:
            logger.warning("Enhance failed for %s: %s", field, e)
            return img

    def _ocr(self, img: Image.Image, field: str) -> str:
        # psm под поле
        psm = self.psm_by_field.get(field, self.default_psm)
        # whitelist и выбор языка
        wl = self.whitelist_by_field.get(field)
        # Текст: kaz+rus+eng; Цифры: eng
        lang = self.lang_digits if wl else (self.lang_text + "+eng")

        cfg = f"--oem 1 --psm {psm}"
        if wl:
            cfg += f" -c tessedit_char_whitelist={wl}"

        return pytesseract.image_to_string(img, lang=lang, config=cfg).strip()

    def _extract_photo(self, image: Image.Image) -> Optional[ContentFile]:
        """
        Вырезает ROI 'photo' и возвращает ContentFile(JPEG).
        """
        try:
            coords = self.coordinates.get("photo")
            if not coords:
                return None
            w, h = image.size
            l, t, r, b = self._to_pixels(coords, w, h)
            if not self._is_valid_box(l, t, r, b, w, h):
                return None

            region = image.crop((l, t, r, b)).convert("RGB")
            bio = io.BytesIO()
            region.save(bio, format="JPEG", quality=90)
            bio.seek(0)
            return ContentFile(bio.getvalue(), name="extracted_photo.jpg")
        except Exception:
            logger.exception("extract_photo failed")
            return None

    # --- пост-обработка текста ---

    def _clean(self, field: str, text: str) -> str:
        # нормализация юникода и базовая чистка пробелов/переводов строк
        text = _normalize_unicode(text)
        text = text.replace("\n", " ").replace("\r", " ").strip()
        text = " ".join(text.split())
        if not text:
            return ""

        if field == "iin":
            m = RE_IIN.search(text)
            return m.group(1) if m else ""

        if field in ("last_name", "first_name", "patronymic"):
            # Сохраняем латиницу + всю кириллицу (включая расширенную \u0400-\u052F),
            # а также дефис и варианты апострофа.
            up = text.upper()
            tokens = []
            for w in up.split():
                w2 = self.name_keep_re.sub("", w)  # вырезаем всё, что не буквы/дефис/апостроф
                if not w2:
                    continue
                if w2 in self.bad_labels:
                    continue
                tokens.append(w2)

            cleaned = " ".join(tokens)
            return _titlecase_cyr(cleaned)

        return text


# Удобная функция-обёртка
def extract_data_from_jpg_coordinates(jpg_path: str) -> Dict:
    parser = JPGCoordinateParser()
    return parser.extract_data_from_jpg(jpg_path)
