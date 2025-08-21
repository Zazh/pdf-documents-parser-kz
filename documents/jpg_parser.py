import re
import os
from PIL import Image, ImageEnhance
import pytesseract
from django.conf import settings
from django.core.files.base import ContentFile
import io
import json


class JPGCoordinateParser:
    """
    Парсер данных из JPG изображений по координатам
    Более простой и надежный чем PDF парсер
    """

    def __init__(self):
        self.coordinates = self.load_coordinates()

    def load_coordinates(self):
        """
        Загружает координаты из файла конфигурации
        """
        try:
            coords_file = os.path.join(settings.BASE_DIR, 'coordinate_config.json')

            if os.path.exists(coords_file):
                with open(coords_file, 'r') as f:
                    saved_coords = json.load(f)
                    return saved_coords
        except Exception as e:
            pass

        # Координаты по умолчанию
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
            'photo': [0.105, 0.163, 0.357, 0.391]
        }

    def extract_data_from_jpg(self, jpg_path):
        """
        Извлекает данные из JPG изображения
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
            'debug_info': {}
        }

        try:
            # Открываем JPG изображение
            image = Image.open(jpg_path)
            width, height = image.size

            # Обрабатываем каждое поле
            for field_name, coords in self.coordinates.items():
                if field_name == 'photo':
                    continue  # Фото обрабатываем отдельно

                # Преобразуем проценты в пиксели
                left = int(coords[0] * width)
                top = int(coords[1] * height)
                right = int(coords[2] * width)
                bottom = int(coords[3] * height)

                # Проверяем корректность координат
                if left < 0 or top < 0 or right > width or bottom > height or left >= right or top >= bottom:
                    continue

                # Извлекаем область
                region = image.crop((left, top, right, bottom))

                # Улучшаем для OCR
                enhanced_region = self.enhance_image_for_ocr(region)

                # Распознаем текст
                text = pytesseract.image_to_string(enhanced_region, lang='rus+eng', config='--psm 7')
                cleaned_text = self.clean_extracted_text(text, field_name)

                # Сохраняем результат
                result[field_name] = cleaned_text

            # Извлекаем фото
            if 'photo' in self.coordinates:
                photo = self.extract_photo_from_jpg(image)
                if photo:
                    result['photo'] = photo

        except Exception as e:
            pass

        return result

    def enhance_image_for_ocr(self, image):
        """
        Улучшает изображение для OCR
        """
        try:
            # Конвертируем в оттенки серого
            if image.mode != 'L':
                gray = image.convert('L')
            else:
                gray = image

            # Увеличиваем контрастность
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(2.0)

            # Увеличиваем резкость
            sharpness_enhancer = ImageEnhance.Sharpness(enhanced)
            sharp = sharpness_enhancer.enhance(1.5)

            # Масштабируем для лучшего OCR
            scale_factor = 2
            new_size = (sharp.width * scale_factor, sharp.height * scale_factor)
            scaled = sharp.resize(new_size, Image.Resampling.LANCZOS)

            return scaled
        except Exception as e:
            print(f"Ошибка улучшения изображения: {e}")
            return image

    def clean_extracted_text(self, text, field_type):
        """
        Очищает извлеченный текст по типу поля
        """
        text = text.strip().replace('\n', ' ').replace('\r', ' ')
        text = ' '.join(text.split())

        if field_type == 'iin':
            # ИИН - только 12 цифр
            digits = ''.join(re.findall(r'\d', text))
            return digits[:12] if len(digits) >= 12 else ''

        elif field_type in ['last_name', 'first_name', 'patronymic']:
            # Имена - только буквы, убираем служебные слова
            words = text.upper().split()
            exclude_words = {'ТЕГІ', 'ФАМИЛИЯ', 'АТЫ', 'ИМЯ', 'ӘКЕСІНІҢ', 'ОТЧЕСТВО'}

            clean_words = []
            for word in words:
                clean_word = re.sub(r'[^А-ЯЁA-Z]', '', word)
                if len(clean_word) > 1 and clean_word not in exclude_words:
                    clean_words.append(clean_word)

            return ' '.join(clean_words)

        elif field_type in ['birth_date', 'issue_date', 'expiry_date']:
            # Даты - ищем формат DD.MM.YYYY
            date_patterns = [
                r'(\d{1,2}[./]\d{1,2}[./]\d{4})',
                r'(\d{1,2}[./]\d{1,2}[./]\d{2})'
            ]

            for pattern in date_patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)

            return re.sub(r'[^\d./]', '', text) if len(text) > 5 else ''

        elif field_type == 'document_number':
            # Номер документа - цифры и буквы
            return re.sub(r'[^А-ЯЁA-Z0-9]', '', text.upper())

        elif field_type in ['birth_place', 'nationality', 'issued_by']:
            # Текстовые поля - минимальная очистка
            return text.upper() if len(text) > 1 else ''

        return text

    def extract_photo_from_jpg(self, image):
        """
        Извлекает фото из JPG
        """
        try:
            coords = self.coordinates['photo']
            width, height = image.size

            left = int(coords[0] * width)
            top = int(coords[1] * height)
            right = int(coords[2] * width)
            bottom = int(coords[3] * height)

            photo_region = image.crop((left, top, right, bottom))

            # Сохраняем как Django файл
            img_io = io.BytesIO()
            photo_region.save(img_io, format='JPEG', quality=90)
            img_io.seek(0)

            return ContentFile(img_io.getvalue(), name='extracted_photo.jpg')

        except Exception as e:
            return None


# Функция для использования в основном коде
def extract_data_from_jpg_coordinates(jpg_path):
    """
    Основная функция для извлечения данных из JPG
    """
    parser = JPGCoordinateParser()
    return parser.extract_data_from_jpg(jpg_path)