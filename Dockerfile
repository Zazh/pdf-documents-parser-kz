FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    fonts-dejavu-core \
    fonts-noto-core \
    fonts-noto-cjk \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    tesseract-ocr-kaz \
  && rm -rf /var/lib/apt/lists/*

# ЯВНО: откуда и куда кладём requirements.txt
# (контекст сборки = ./datas, у тебя файл реально лежит тут)
COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /app/requirements.txt \
 && pip install --no-cache-dir gunicorn

# ЯВНО: копируем весь код проекта в /app
COPY . /app

EXPOSE 8005

CMD ["python", "manage.py", "runserver", "0.0.0.0:8005"]
