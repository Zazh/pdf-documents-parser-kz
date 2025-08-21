# jpg_parser.py
import os
import re
import io
import json
import logging
from typing import Dict, Tuple

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
    # простая валидация
    if 1 <= d <= 31 and 1 <= mth <= 12 and 1900 <= y <= 2100:
        return f"{d:02d}.{mth:02d}.{y}"
    return ""

# ---------------------
# ОСНОВНОЙ ПАРСЕР ROI
# ---------------------

class JPGCoordinateParser:
    """
    Извлекает поля из JPG по заданным координатам (нормализованные 0..1).
    Никаких поисков по тексту — только точечный OCR каждой ROI.
    """

    def __init__(
        self,
        lang_text: str = "kaz+rus",   # нужен пакет tesseract-ocr-kaz
        lang_digits: str = "eng",
        default_psm: int = 7,         # одна строка
    ):
        self.lang_text = lang_text
        self.lang_digits = lang_digits
        self.default_psm = default_psm
        self.coordinates = self.load_coordinates()

        # Спец-настройки на поле
        self.psm_by_field: Dict[str, int] = {
            "iin": 7, "birth_date": 7, "issue_date": 7, "expiry_date": 7,
            "document_number": 7,
            # текстовые поля могут быть строкой; если блок — поставь 6
            "last_name": 7, "first_name": 7, "patronymic": 7,
            "birth_place": 6, "nationality": 6, "issued_by": 6,
        }

        self.whitelist_by_field: Dict[str, str] = {
            "iin": "0123456789",
            "birth_date": "0123456789./",
            "issue_date": "0123456789./",
            "expiry_date": "0123456789./",
            "document_number": "ABCDEFGHIJKLMNOPQRSTUVWXYZАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ0123456789",
        }

    # ---------- загрузка координат ----------

    def load_coordinates(self) -> Dict[str, Tuple[float, float, float, float]]:
        try:
            coords_file = os.path.join(settings.BASE_DIR, "coordinate_config.json")
            if os.path.exists(coords_file):
                with open(coords_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # sanity-check нормализации
                    for k, v in list(data.items()):
                        if not (isinstance(v, (list, tuple)) and len(v) == 4):
                            logger.warning("Bad coords for %s, dropping", k)
                            data.pop(k, None)
                    if data:
                        return data
        except Exception:
            logger.exception("Failed to load coordinate_config.json")

        # дефолт (как у тебя)
        return {
            'last_name': [0.389, 0.190, 0.873, 0.225],
            'first_name': [0.388, 0.243, 0.874, 0.278],
            'patronymic': [0.390, 0.304, 0.885, 0.328],
            'birth_date': [0.385, 0.353, 0.541, 0.381],
            'iin': [0.183, 0.407, 0.404, 0.438],
            'birth_place': [0.31, 0.537, 0.891, 0.560],
            'nationality': [0.307, 0.576, 0.851, 0.597],
            'document_number': [0.721, 0.482, 0.890, 0.514],
            'issued_by': [0.311, 0.610, 0.922, 0.635],
            'issue_date': [0.307, 0.646, 0.455, 0.667],
            'expiry_date': [0.471, 0.646, 0.670, 0.671],
            'photo': [0.105, 0.163, 0.357, 0.391],
        }

    # ---------- публичный API ----------

    def extract_data_from_jpg(self, jpg_path: str) -> Dict:
        result = {
            'first_name': '', 'last_name': '', 'patronymic': '',
            'birth_date': '', 'iin': '', 'birth_place': '',
            'nationality': '', 'issued_by': '', 'issue_date': '',
            'expiry_date': '', 'document_number': '',
            'photo': None, 'debug_info': {}
        }

        try:
            image = Image.open(jpg_path)
            width, height = image.size

            # сначала текстовые/числовые поля
            for field, coords in self.coordinates.items():
                if field == "photo":
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
                # для дебага можно сохранять «как видит тессеракт»
                result['debug_info'][field] = {
                    'bbox': [l, t, r, b],
                    'raw': text,
                }

            # затем фото (отдельно)
            if 'photo' in self.coordinates:
                result['photo'] = self._extract_photo(image)

            # финальные валидации/нормализации
            if result['iin']:
                if not validate_iin(result['iin']):
                    # если OCR ошибся одной цифрой — вернём как есть, но пометим
                    result['debug_info'].setdefault('warnings', []).append('IIN checksum failed')

            for dfield in ('birth_date', 'issue_date', 'expiry_date'):
                if result[dfield]:
                    norm = normalize_date(result[dfield])
                    if norm:
                        result[dfield] = norm

        except Exception:
            logger.exception("extract_data_from_jpg failed for %s", jpg_path)

        return result

    # ---------- помощьники ----------

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
        - в градации серого
        - автоконтраст
        - лёгкая контрастность
        - апскейл ТОЛЬКО если ROI маленькая
        """
        try:
            if img.mode != 'L':
                img = img.convert('L')

            # автоматический контраст — мягче, чем жёсткий порог
            img = ImageOps.autocontrast(img)

            # немного усилим контраст
            img = ImageEnhance.Contrast(img).enhance(1.6)

            # доводка резкости
            img = ImageEnhance.Sharpness(img).enhance(1.3)

            # апскейл только при узкой ROI (ускоряет общий случай)
            min_side = min(img.size)
            if min_side < 40:
                scale = 2.0
            elif min_side < 80:
                scale = 1.5
            else:
                scale = 1.2 if field in ("iin", "document_number", "birth_date", "issue_date", "expiry_date") else 1.0

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
        lang = self.lang_digits if wl else (self.lang_text + "+eng")  # текст: kaz+rus+eng; цифры: eng

        cfg = f"--oem 1 --psm {psm}"
        if wl:
            cfg += f" -c tessedit_char_whitelist={wl}"

        return pytesseract.image_to_string(img, lang=lang, config=cfg).strip()

    def _clean(self, field: str, text: str) -> str:
        text = text.replace("\n", " ").replace("\r", " ").strip()
        text = " ".join(text.split())

        if not text:
            return ""

        if field == "iin":
            m = RE_IIN.search(text)
            return m.group(1) if m else ""

        if field in ("birth_date", "issue_date", "expiry_date"):
            return normalize_date(text) or re.sub(r"[^0-9./]", "", text)

        if field == "document_number":
            return re.sub(r"[^A-ZА-ЯЁ0-9]", "", text.upper())

        if field in ("last_name", "first_name", "patronymic"):
            # только буквы, убрать служебные слова, дефисы оставить
            tokens = [re.sub(r"[^A-ZА-ЯЁ-]", "", w.upper()) for w in text.split()]
            bad = {"ТЕГІ", "ФАМИЛИЯ", "АТЫ", "ИМЯ", "ӘКЕСІНІҢ", "ОТЧЕСТВО"}
            words = [w for w in tokens if len(w) > 1 and w not in bad]
            return " ".join(words)

        if field in ("birth_place", "nationality", "issued_by"):
            return text.upper()

        return text

    def _extract_photo(self, image: Image.Image):
        try:
            coords = self.coordinates['photo']
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


# Удобная функция-обёртка
def extract_data_from_jpg_coordinates(jpg_path: str) -> Dict:
    parser = JPGCoordinateParser()
    return parser.extract_data_from_jpg(jpg_path)
