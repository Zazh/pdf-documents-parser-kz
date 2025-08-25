from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from datetime import datetime

import os

from django.views.decorators.http import require_POST

from .models import Document
from .forms import DocumentUploadForm
from .utils import extract_data_from_pdf


@login_required
def upload_document(request):
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.save()

            try:
                pdf_path = document.pdf_file.path
                print(f"Обрабатываем PDF: {pdf_path}")

                extracted = extract_data_from_pdf(pdf_path)

                # Записываем только нужное
                document.last_name  = extracted.get('last_name', '')
                document.first_name = extracted.get('first_name', '')
                document.patronymic = extracted.get('patronymic', '')
                document.iin        = extracted.get('iin', '')

                # Сохраняем фото, если извлеклось
                if extracted.get('photo'):
                    document.photo = extracted['photo']

                # Остальные поля чистим (НО фото НЕ трогаем)
                document.birth_place     = ''
                document.nationality     = ''
                document.birth_date      = ''
                document.issued_by       = ''
                document.issue_date      = ''
                document.expiry_date     = ''
                document.document_number = ''
                document.raw_text        = ''
                document.jpg_file        = None

                document.save()

                # Сообщение
                pretty_name = f"{document.first_name} {document.patronymic}".strip()
                found = []
                if document.last_name:  found.append(f"Фамилия: {document.last_name}")
                if pretty_name:         found.append(f"Имя Отчество: {pretty_name}")
                if document.iin:        found.append(f"ИИН: {document.iin}")
                if document.photo:      found.append("Фото: ✓")

                messages.success(request, "Документ обработан! " + (", ".join(found) if found else "Данных нет"))
                return redirect('document_detail', pk=document.pk)

            except Exception as e:
                messages.error(request, f'Ошибка при обработке документа: {str(e)}')
                return redirect('upload_document')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме')
    else:
        form = DocumentUploadForm()

    return render(request, 'documents/upload.html', {'form': form})


@login_required
def document_list(request):
    """
    Список всех обработанных документов
    """
    documents = Document.objects.all().order_by('-created_at')
    return render(request, 'documents/document_list.html', {'documents': documents})


@login_required
def document_detail(request, pk):
    """
    Детальная информация о документе
    """
    try:
        document = Document.objects.get(pk=pk)
    except Document.DoesNotExist:
        messages.error(request, 'Документ не найден')
        return redirect('document_list')

    return render(request, 'documents/document_detail.html', {'document': document})


@csrf_exempt
def get_coordinates(request):
    try:
        import json, os
        from django.conf import settings

        coords_file = os.path.join(settings.BASE_DIR, 'coordinate_config.json')
        if os.path.exists(coords_file):
            with open(coords_file, 'r') as f:
                raw = json.load(f)
                # включаем photo
                keys = {'last_name', 'first_name', 'patronymic', 'iin', 'photo'}
                coordinates = {k: v for k, v in raw.items() if k in keys}
        else:
            coordinates = {
                'last_name':   [0.389, 0.190, 0.873, 0.225],
                'first_name':  [0.388, 0.243, 0.874, 0.278],
                'patronymic':  [0.390, 0.304, 0.885, 0.328],
                'iin':         [0.183, 0.407, 0.404, 0.438],
                'photo':       [0.105, 0.163, 0.357, 0.391],
            }

        return JsonResponse({'success': True, 'coordinates': coordinates})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def coordinate_admin(request):
    """
    Админ-панель для управления координатами
    """
    return render(request, 'documents/coordinate_admin.html')


@csrf_exempt
def save_coordinates(request):
    """
    API для сохранения координат из калибровки
    """
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)

            # Сохраняем координаты в файл или базу данных
            # Для простоты сохраним в файл
            import os
            from django.conf import settings

            coords_file = os.path.join(settings.BASE_DIR, 'coordinate_config.json')

            with open(coords_file, 'w') as f:
                json.dump(data, f, indent=2)

            return JsonResponse({'success': True, 'message': 'Координаты сохранены'})

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Только POST запросы'})


@csrf_exempt
def api_upload_document(request):
    if request.method == 'POST' and request.FILES.get('pdf_file'):
        try:
            document = Document.objects.create(pdf_file=request.FILES['pdf_file'])

            pdf_path = document.pdf_file.path
            extracted = extract_data_from_pdf(pdf_path)

            document.last_name  = extracted.get('last_name', '')
            document.first_name = extracted.get('first_name', '')
            document.patronymic = extracted.get('patronymic', '')
            document.iin        = extracted.get('iin', '')

            # Сохраняем фото, если есть
            if extracted.get('photo'):
                document.photo = extracted['photo']

            # Чистим остальное (фото НЕ трогаем)
            document.birth_place     = ''
            document.nationality     = ''
            document.birth_date      = ''
            document.issued_by       = ''
            document.issue_date      = ''
            document.expiry_date     = ''
            document.document_number = ''
            document.raw_text        = ''
            document.jpg_file        = None

            document.save()

            return JsonResponse({
                'success': True,
                'document_id': document.pk,
                'data': {
                    'last_name': document.last_name,
                    'first_name': document.first_name,
                    'patronymic': document.patronymic,
                    'iin': document.iin,
                    'photo_url': document.photo.url if document.photo else None
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Неправильный запрос'})

@login_required
def coordinate_calibration(request):
    """
    Страница для калибровки координат извлечения данных
    """
    return render(request, 'documents/coordinate_calibration.html')


@login_required
def test_jpg_parsing(request):
    """
    Тестовая страница для отладки JPG парсинга
    """
    if request.method == 'POST' and request.FILES.get('jpg_file'):
        try:
            jpg_file = request.FILES['jpg_file']

            # Сохраняем временно
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                for chunk in jpg_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            # Тестируем парсинг
            from .jpg_parser import extract_data_from_jpg_coordinates
            result = extract_data_from_jpg_coordinates(tmp_path)

            # Удаляем временный файл
            os.unlink(tmp_path)

            return render(request, 'documents/test_jpg.html', {
                'result': result,
                'success': True
            })

        except Exception as e:
            return render(request, 'documents/test_jpg.html', {
                'error': str(e),
                'success': False
            })

    return render(request, 'documents/test_jpg.html')

@login_required
@require_POST
def set_test_date(request, pk):
    document = get_object_or_404(Document, pk=pk)
    value = (request.POST.get('test_date') or '').strip()
    if not value:
        messages.error(request, 'Укажите дату и время.')
        return redirect('document_detail', pk=pk)

    # HTML5 datetime-local приходит как 'YYYY-MM-DDTHH:MM'
    dt = parse_datetime(value.replace('T', ' '))
    if dt is None:
        try:
            dt = datetime.strptime(value, '%Y-%m-%dT%H:%M')
        except ValueError:
            messages.error(request, 'Неверный формат даты.')
            return redirect('document_detail', pk=pk)

    if dt.tzinfo is None:
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    document.test_date = dt
    document.save(update_fields=['test_date'])
    messages.success(request, 'Дата тестирования обновлена.')
    return redirect('document_detail', pk=pk)


def home(request):
    """
    Главная страница
    """
    if request.user.is_authenticated:
        return redirect('upload_document')
    else:
        return render(request, 'documents/upload.html')