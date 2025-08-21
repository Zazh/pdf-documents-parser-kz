from django import forms
from .models import Document


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['pdf_file']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pdf_file'].widget.attrs.update({
            'class': 'form-control',
            'accept': '.pdf',
            'required': True
        })
        self.fields['pdf_file'].help_text = 'Выберите PDF файл удостоверения личности'

    def clean_pdf_file(self):
        pdf_file = self.cleaned_data.get('pdf_file')

        if pdf_file:
            # Проверяем размер файла (максимум 10 МБ)
            if pdf_file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Файл слишком большой. Максимальный размер: 10 МБ')

            # Проверяем расширение
            if not pdf_file.name.lower().endswith('.pdf'):
                raise forms.ValidationError('Файл должен быть в формате PDF')

        return pdf_file