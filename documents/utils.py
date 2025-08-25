# utils.py
import re
import logging
from typing import Optional, Dict

from pdf2image import convert_from_path

logger = logging.getLogger(__name__)

def convert_pdf_to_jpg(pdf_path: str, dpi: int = 220) -> Optional[str]:
    """
    Рендерит 1-ю страницу PDF в JPG. DPI=220 обычно достаточно и быстрее 300.
    Вернёт путь к JPG либо None.
    """
    try:
        images = convert_from_path(
            pdf_path,
            dpi=dpi,
            first_page=1,
            last_page=1,
            fmt="jpeg"  # сразу JPEG
        )
        if not images:
            return None

        jpg_path = re.sub(r"\.(pdf|PDF)$", ".jpg", pdf_path)
        images[0].save(jpg_path, "JPEG", quality=90, optimize=True)
        return jpg_path
    except Exception:
        logger.exception("convert_pdf_to_jpg failed for %s", pdf_path)
        return None


def extract_data_from_pdf(pdf_path: str) -> Dict:
    """
    PDF -> JPG -> координатный OCR (только Фамилия, Имя, Отчество, ИИН).
    """
    result = {'first_name': '', 'last_name': '', 'patronymic': '', 'iin': '', 'photo': None}

    jpg_path = convert_pdf_to_jpg(pdf_path)
    if not jpg_path:
        return result

    try:
        from .jpg_parser import extract_data_from_jpg_coordinates
        coord_result = extract_data_from_jpg_coordinates(jpg_path)
        if coord_result:
            # оставим только нужные
            for k in ('first_name', 'last_name', 'patronymic', 'iin', 'photo'):
                result[k] = coord_result.get(k, result.get(k))
    except Exception:
        logger.exception("extract_data_from_pdf: coordinate parser failed")

    return result


def extract_data_from_image(image_path: str) -> Dict:
    from .jpg_parser import extract_data_from_jpg_coordinates
    coord_result = extract_data_from_jpg_coordinates(image_path)
    return {
        'first_name': coord_result.get('first_name', ''),
        'last_name': coord_result.get('last_name', ''),
        'patronymic': coord_result.get('patronymic', ''),
        'iin': coord_result.get('iin', '')
    }