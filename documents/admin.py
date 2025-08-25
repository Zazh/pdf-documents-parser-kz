from django.contrib import admin
from .models import Document

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['id', 'get_full_name', 'iin', 'birth_date', 'test_date', 'created_at', 'has_photo']
    list_filter  = ['created_at', 'test_date', 'nationality', 'issued_by']
    search_fields = ['first_name', 'last_name', 'patronymic', 'iin', 'document_number']
    readonly_fields = ['created_at']  # test_date редактируемое поле
    ordering = ['-created_at']
    date_hierarchy = 'test_date'      # быстрая навигация по датам

    def get_full_name(self, obj):
        parts = [obj.last_name, obj.first_name, obj.patronymic]
        return ' '.join(filter(None, parts)) or f"Документ #{obj.id}"
    get_full_name.short_description = 'ФИО'

    def has_photo(self, obj):
        return bool(obj.photo)
    has_photo.boolean = True
    has_photo.short_description = 'Фото'

    fieldsets = (
        ('Загруженный файл', {'fields': ('pdf_file',)}),
        ('Личные данные', {
            'fields': ('last_name', 'first_name', 'patronymic', 'birth_date', 'iin', 'birth_place', 'nationality')
        }),
        ('Тестирование', {'fields': ('test_date',)}),
        ('Данные документа', {'fields': ('document_number', 'issued_by', 'issue_date', 'expiry_date')}),
        ('Медиа', {'fields': ('photo',)}),
        ('Отладочная информация', {
            'fields': ('raw_text', 'created_at'),
            'classes': ('collapse',)
        }),
    )
