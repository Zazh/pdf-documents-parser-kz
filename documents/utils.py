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
    Высокоуровневая функция: PDF -> JPG -> координатный OCR.
    Никакого поиска по тексту — только ROI.
    """
    result = {
        'first_name': '', 'last_name': '', 'patronymic': '',
        'birth_date': '', 'iin': '', 'birth_place': '',
        'nationality': '', 'issued_by': '', 'issue_date': '',
        'expiry_date': '', 'document_number': '',
        'photo': None, 'raw_text': ''
    }

    jpg_path = convert_pdf_to_jpg(pdf_path)
    if not jpg_path:
        return result

    try:
        # импортируем локально, чтобы избежать циклических импортов
        from .jpg_parser import extract_data_from_jpg_coordinates
        coord_result = extract_data_from_jpg_coordinates(jpg_path)
        if coord_result:
            result.update(coord_result)
    except Exception:
        logger.exception("extract_data_from_pdf: coordinate parser failed")

    return result


def extract_data_from_image(image_path: str) -> Dict:
    """
    Если приходит уже JPG/PNG — сразу координатный парсер.
    Удобная обёртка, чтобы не плодить дубли в коде.
    """
    from .jpg_parser import extract_data_from_jpg_coordinates
    return extract_data_from_jpg_coordinates(image_path)
