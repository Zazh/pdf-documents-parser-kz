from django.db import models
from django.utils import timezone


class Document(models.Model):
    # Загруженные файлы
    pdf_file = models.FileField(upload_to='pdfs/', verbose_name="PDF файл")
    jpg_file = models.ImageField(upload_to='jpgs/', blank=True, null=True, verbose_name="JPG изображение")

    # Дата экзамена
    test_date = models.DateTimeField(
        verbose_name="Дата тестирования",
        default=timezone.now,
        db_index=True,
    )
    # Основные данные
    first_name = models.CharField(max_length=100, blank=True, verbose_name="Имя")
    last_name = models.CharField(max_length=100, blank=True, verbose_name="Фамилия")
    patronymic = models.CharField(max_length=100, blank=True, verbose_name="Отчество")
    iin = models.CharField(max_length=12, blank=True, verbose_name="ИИН")

    # Дополнительные данные
    birth_place = models.CharField(max_length=200, blank=True, verbose_name="Место рождения")
    nationality = models.CharField(max_length=100, blank=True, verbose_name="Национальность")
    birth_date = models.CharField(max_length=20, blank=True, verbose_name="Дата рождения")

    # Данные о документе
    issued_by = models.CharField(max_length=200, blank=True, verbose_name="Кем выдан")
    issue_date = models.CharField(max_length=20, blank=True, verbose_name="Дата выдачи")
    expiry_date = models.CharField(max_length=20, blank=True, verbose_name="Дата окончания")
    document_number = models.CharField(max_length=50, blank=True, verbose_name="Номер документа")

    # Медиа
    photo = models.ImageField(upload_to='photos/', blank=True, null=True, verbose_name="Фото")

    # Служебные поля
    raw_text = models.TextField(blank=True, verbose_name="Извлеченный текст")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"
        ordering = ['-created_at']

    def __str__(self):
        if self.first_name or self.last_name:
            full_name = f"{self.last_name} {self.first_name}"
            if self.patronymic:
                full_name += f" {self.patronymic}"
            return f"{full_name} ({self.iin})"
        return f"Документ #{self.id}"