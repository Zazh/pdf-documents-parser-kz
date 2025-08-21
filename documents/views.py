from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
import os
from .models import Document
from .forms import DocumentUploadForm
from .utils import extract_data_from_pdf


@login_required
def upload_document(request):
    """
    Страница загрузки PDF документов
    """
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)

        if form.is_valid():
            # Сохраняем загруженный файл
            document = form.save(commit=False)
            document.save()

            # Обрабатываем PDF в фоне
            try:
                pdf_path = document.pdf_file.path
                print(f"Обрабатываем PDF: {pdf_path}")

                # Конвертируем PDF в JPG и сохраняем
                from .utils import convert_pdf_to_jpg
                jpg_path = convert_pdf_to_jpg(pdf_path)

                if jpg_path:
                    # Сохраняем JPG в модель
                    from django.core.files import File
                    import os
                    with open(jpg_path, 'rb') as jpg_file:
                        document.jpg_file.save(
                            os.path.basename(jpg_path),
                            File(jpg_file),
                            save=False
                        )

                # Извлекаем данные
                extracted_data = extract_data_from_pdf(pdf_path)

                # Обновляем модель с извлеченными данными
                document.first_name = extracted_data.get('first_name', '')
                document.last_name = extracted_data.get('last_name', '')
                document.patronymic = extracted_data.get('patronymic', '')
                document.birth_date = extracted_data.get('birth_date', '')
                document.iin = extracted_data.get('iin', '')
                document.birth_place = extracted_data.get('birth_place', '')
                document.nationality = extracted_data.get('nationality', '')
                document.issued_by = extracted_data.get('issued_by', '')
                document.issue_date = extracted_data.get('issue_date', '')
                document.expiry_date = extracted_data.get('expiry_date', '')
                document.document_number = extracted_data.get('document_number', '')
                document.raw_text = extracted_data.get('raw_text', '')

                if extracted_data.get('photo'):
                    document.photo = extracted_data['photo']

                document.save()

                # Сообщение об успехе
                found_fields = []
                if document.iin: found_fields.append(f"ИИН: {document.iin}")
                if document.first_name: found_fields.append(f"Имя: {document.first_name}")
                if document.last_name: found_fields.append(f"Фамилия: {document.last_name}")

                success_msg = f"Документ обработан! Найдено: {', '.join(found_fields) if found_fields else 'данные извлекаются...'}"
                messages.success(request, success_msg)
                return redirect('document_detail', pk=document.pk)

            except Exception as e:
                messages.error(request, f'Ошибка при обработке документа: {str(e)}')
                return redirect('upload_document')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме')
    else:
        form = DocumentUploadForm()

    # Возвращаем красивый шаблон
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
    """
    API для получения текущих координат
    """
    try:
        import json
        import os
        from django.conf import settings

        coords_file = os.path.join(settings.BASE_DIR, 'coordinate_config.json')

        if os.path.exists(coords_file):
            with open(coords_file, 'r') as f:
                coordinates = json.load(f)
        else:
            # Координаты по умолчанию
            coordinates = {
                'last_name': [0.389, 0.190, 0.873, 0.225],
                'first_name': [0.388, 0.243, 0.874, 0.278],
                'iin': [0.183, 0.407, 0.404, 0.438],
                'photo': [0.105, 0.161, 0.360, 0.392]
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
    """
    API endpoint для загрузки документов (если нужен)
    """
    if request.method == 'POST' and request.FILES.get('pdf_file'):
        try:
            # Создаем документ
            document = Document.objects.create(
                pdf_file=request.FILES['pdf_file']
            )

            # Обрабатываем PDF
            pdf_path = document.pdf_file.path
            extracted_data = extract_data_from_pdf(pdf_path)

            # Обновляем данные
            document.first_name = extracted_data.get('first_name', '')
            document.last_name = extracted_data.get('last_name', '')
            document.iin = extracted_data.get('iin', '')

            if extracted_data.get('photo'):
                document.photo = extracted_data['photo']

            document.save()

            return JsonResponse({
                'success': True,
                'document_id': document.pk,
                'data': {
                    'first_name': document.first_name,
                    'last_name': document.last_name,
                    'iin': document.iin,
                    'photo_url': document.photo.url if document.photo else None
                }
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })

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


def home(request):
    """
    Главная страница
    """
    if request.user.is_authenticated:
        return redirect('upload_document')
    else:
        return render(request, 'documents/upload.html')