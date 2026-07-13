FROM python:3.12-slim

# Instala Calibre (para ebook-convert, ebook-meta, calibredb) vía apt,
# en lugar de compilarlo o instalar sus dependencias internas por pip.
RUN apt-get update && apt-get install -y --no-install-recommends \
    calibre \
    wget \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
