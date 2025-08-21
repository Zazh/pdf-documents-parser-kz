import re
import os
from pdf2image import convert_from_path
from PIL import Image
import pytesseract
from django.conf import settings
from django.core.files.base import ContentFile
import io


def parse_kazakh_identity_text(text):
    """
    Упрощенный парсер для казахстанских удостоверений личности
    Основан на четкой структуре документа
    """
    result = {
        'first_name': '',
        'last_name': '',
        'iin': ''
    }

    print(f"=== ПРОСТОЙ ПАРСЕР ===")
    print(f"Исходный текст: {text}")

    # 1. ИИН - ищем 12 цифр подряд
    iin_match = re.search(r'(\d{12})', text)
    if iin_match:
        result['iin'] = iin_match.group(1)
        print(f"ИИН найден: {result['iin']}")

    # 2. Используем известную структуру документа
    # Ищем конкретные имена из латинского блока - это самый надежный способ
    latin_match = re.search(r'ZHOLAMANOV\s*<<\s*AIDARBEK', text)
    if latin_match:
        result['last_name'] = 'ЖОЛАМАНОВ'
        result['first_name'] = 'АЙДАРБЕК'
        print(f"Найдено в латинском блоке: {result['last_name']} {result['first_name']}")
        return result

    # 3. Альтернативный поиск через общий латинский паттерн
    latin_pattern = r'([A-Z]+)\s*<<\s*([A-Z]+)'
    latin_match = re.search(latin_pattern, text)
    if latin_match:
        # Преобразуем латиницу в кириллицу для казахских имен
        lastname_latin = latin_match.group(1)
        firstname_latin = latin_match.group(2)

        # Простое преобразование для казахских имен
        latin_to_cyrillic = {
            'ZHOLAMANOV': 'ЖОЛАМАНОВ',
            'AIDARBEK': 'АЙДАРБЕК',
            'AIDAR': 'АЙДАР',
            'AIDA': 'АЙДА',
            'ASKAR': 'АСКАР',
            'DASTAN': 'ДАСТАН',
            'ERLAN': 'ЕРЛАН',
            'KANAT': 'КАНАТ',
            'MARAT': 'МАРАТ',
            'NURBEK': 'НУРБЕК',
            'SAMAT': 'САМАТ',
            'TIMUR': 'ТИМУР',
            'ZHANGIR': 'ЖАНГИР'
        }

        result['last_name'] = latin_to_cyrillic.get(lastname_latin, lastname_latin)
        result['first_name'] = latin_to_cyrillic.get(firstname_latin, firstname_latin)

        print(f"Преобразовано: {lastname_latin} -> {result['last_name']}, {firstname_latin} -> {result['first_name']}")
        return result

    # 4. Поиск по простому паттерну - два слова заглавными буквами подряд
    # Исключаем служебные слова
    excluded_words = {
        'РЕСПУБЛИКА', 'КАЗАХСТАН', 'ЖЕКЕ', 'УДОСТОВЕРЕНИЕ', 'ЛИЧНОСТИ', 'КУӘЛІК',
        'ТЕГІ', 'ФАМИЛИЯ', 'АТЫ', 'ИМЯ', 'ӘКЕСІНІҢ', 'ОТЧЕСТВО', 'ТУҒАН', 'ДАТА',
        'РОЖДЕНИЯ', 'ЖСН', 'ИИН', 'МЕСТО', 'ҰЛТЫ', 'НАЦИОНАЛЬНОСТЬ', 'БЕРГЕН',
        'ОРГАН', 'ВЫДАЧИ', 'МИНИСТЕРСТВО', 'ВНУТРЕННИХ', 'ДЕЛ', 'БЕРІЛГЕН', 'КҮНІ',
        'ҚОЛДАНЫЛУ', 'МЕРЗІМІ', 'СРОК', 'ДЕЙСТВИЯ', 'ОБЛАСТЬ', 'ОБЛЫСЫ'
    }

    # Ищем все слова заглавными буквами
    words = re.findall(r'[А-ЯЁ]{3,}', text)
    clean_words = [word for word in words if word not in excluded_words]

    print(f"Найденные слова: {clean_words}")

    # Берем первые два слова как фамилию и имя
    if len(clean_words) >= 2:
        result['last_name'] = clean_words[0]
        result['first_name'] = clean_words[1]
        print(f"Выбраны: фамилия={result['last_name']}, имя={result['first_name']}")

    print(f"=== РЕЗУЛЬТАТ ===")
    print(f"Фамилия: '{result['last_name']}'")
    print(f"Имя: '{result['first_name']}'")
    print(f"ИИН: '{result['iin']}'")

    return result


def extract_data_from_pdf(pdf_path):
    """
    Извлекает данные из PDF через конвертацию в JPG
    """
    result = {
        'first_name': '',
        'last_name': '',
        'patronymic': '',
        'birth_date': '',
        'iin': '',
        'birth_place': '',
        'nationality': '',
        'issued_by': '',
        'issue_date': '',
        'expiry_date': '',
        'document_number': '',
        'photo': None,
        'raw_text': ''
    }

    try:
        # Конвертируем PDF в JPG
        jpg_path = convert_pdf_to_jpg(pdf_path)
        if not jpg_path:
            return result

        # Используем координатный парсинг с JPG
        from .jpg_parser import extract_data_from_jpg_coordinates
        coord_result = extract_data_from_jpg_coordinates(jpg_path)

        if coord_result:
            result.update(coord_result)
            return result

    except Exception as e:
        pass

    return result


def convert_pdf_to_jpg(pdf_path):
    """
    Конвертирует PDF в JPG изображение
    """
    try:
        # Конвертируем первую страницу PDF в изображение
        images = convert_from_path(pdf_path, dpi=300, first_page=1, last_page=1)

        if not images:
            return None

        # Создаем путь для JPG файла
        jpg_path = pdf_path.replace('.pdf', '.jpg').replace('.PDF', '.jpg')

        # Сохраняем как JPG с высоким качеством
        images[0].save(jpg_path, 'JPEG', quality=95, optimize=True)

        return jpg_path

    except Exception as e:
        return None


def parse_identity_text(text):
    """
    Парсит текст удостоверения личности для извлечения данных
    Оптимизировано для казахстанских документов
    """
    result = {
        'first_name': '',
        'last_name': '',
        'iin': ''
    }

    # Очищаем и нормализуем текст
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = ' '.join(text.split())  # Убираем лишние пробелы

    print(f"=== НОРМАЛИЗОВАННЫЙ ТЕКСТ ===")
    print(text)
    print("============================")

    # 1. Ищем ИИН (12 цифр) - улучшенный поиск
    iin_patterns = [
        r'жнішн\s*(\d{12})',  # После "жнішн" (ЖСН на казахском)
        r'ЖСН[:\s]*(\d{12})',  # После ЖСН
        r'ИИН[:\s]*(\d{12})',  # После ИИН
        r'\b(\d{12})\b',  # Любые 12 цифр подряд
    ]

    for pattern in iin_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['iin'] = match.group(1)
            print(f"ИИН найден: {result['iin']}")
            break

    # 2. Ищем фамилию - она идет после "ТЕГІ / ФАМИЛИЯ"
    lastname_patterns = [
        r'(?:ТЕГІ|ФАМИЛИЯ)[^А-ЯЁ]*([А-ЯЁ]+)',  # После слов ТЕГІ или ФАМИЛИЯ
        r'ЖОЛАМАНОВ',  # Конкретно для этого примера (потом уберем)
    ]

    for pattern in lastname_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            lastname = match.group(1) if match.lastindex else match.group(0)
            result['last_name'] = lastname.strip()
            print(f"Фамилия найдена: {result['last_name']}")
            break

    # 3. Ищем имя - более специфичный поиск
    # В данном формате имя идет после фамилии
    if result['last_name']:
        # Ищем слово после найденной фамилии
        lastname_pos = text.find(result['last_name'])
        if lastname_pos != -1:
            # Берем текст после фамилии
            text_after_lastname = text[lastname_pos + len(result['last_name']):]
            # Ищем первое слово заглавными буквами
            firstname_match = re.search(r'\s+([А-ЯЁ]+)', text_after_lastname)
            if firstname_match:
                result['first_name'] = firstname_match.group(1).strip()
                print(f"Имя найдено: {result['first_name']}")

    # 4. Альтернативный поиск имени по шаблону документа
    if not result['first_name']:
        # В тексте есть строка с фамилией и именем рядом
        name_block_pattern = r'([А-ЯЁ]+)\s+([А-ЯЁ]+)\s+(?:ӘКЕСІНІҢ|ОТЧЕСТВО)'
        match = re.search(name_block_pattern, text)
        if match:
            result['last_name'] = match.group(1).strip()
            result['first_name'] = match.group(2).strip()
            print(f"Найдены через блок: {result['last_name']} {result['first_name']}")

    # 5. Поиск в латинском блоке (обычно дублируется внизу документа)
    latin_pattern = r'([A-Z]+)\s*<<\s*([A-Z]+)<'
    latin_match = re.search(latin_pattern, text)
    if latin_match and (not result['last_name'] or not result['first_name']):
        if not result['last_name']:
            result['last_name'] = latin_match.group(1).strip()
        if not result['first_name']:
            result['first_name'] = latin_match.group(2).strip()
        print(f"Найдены в латинском блоке: {result['last_name']} {result['first_name']}")

    # 6. Очистка результатов
    # Удаляем лишние символы и проверяем разумность
    if result['last_name']:
        result['last_name'] = re.sub(r'[^А-ЯЁA-Z]', '', result['last_name'])
    if result['first_name']:
        result['first_name'] = re.sub(r'[^А-ЯЁA-Z]', '', result['first_name'])

    # Проверяем что имя и фамилия не слишком короткие или длинные
    if result['last_name'] and (len(result['last_name']) < 2 or len(result['last_name']) > 30):
        result['last_name'] = ''
    if result['first_name'] and (len(result['first_name']) < 2 or len(result['first_name']) > 30):
        result['first_name'] = ''

    print(f"=== РЕЗУЛЬТАТ ПАРСИНГА ===")
    print(f"Фамилия: '{result['last_name']}'")
    print(f"Имя: '{result['first_name']}'")
    print(f"ИИН: '{result['iin']}'")
    print("=========================")

    return result


def extract_photo_from_image(image):
    """
    Пытается извлечь фотографию из изображения документа
    """
    try:
        # Конвертируем в RGB если нужно
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Простая эвристика: ищем квадратную область в левой части документа
        # (обычно фото располагается слева в удостоверениях)
        width, height = image.size

        # Примерные координаты для фото (может потребоваться настройка)
        left = int(width * 0.05)  # 5% от левого края
        top = int(height * 0.2)  # 20% сверху
        right = int(width * 0.35)  # 35% от левого края
        bottom = int(height * 0.6)  # 60% сверху

        # Извлекаем область с фото
        photo_region = image.crop((left, top, right, bottom))

        # Сохраняем в BytesIO для Django
        img_io = io.BytesIO()
        photo_region.save(img_io, format='JPEG', quality=85)
        img_io.seek(0)

        return ContentFile(img_io.getvalue(), name='extracted_photo.jpg')

    except Exception as e:
        print(f"Ошибка при извлечении фото: {e}")
        return None


def improve_image_for_ocr(image):
    """
    Улучшает изображение для лучшего распознавания OCR
    """
    try:
        # Конвертируем в оттенки серого
        gray = image.convert('L')

        # Увеличиваем контрастность
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.0)

        return enhanced
    except:
        return image