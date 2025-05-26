# Użyj oficjalnego obrazu Python
FROM python:3.11-slim

# Ustaw katalog roboczy w kontenerze
WORKDIR /app

# Skopiuj plik z zależnościami
COPY requirements.txt .

# Zainstaluj zależności
RUN pip install --no-cache-dir -r requirements.txt

# Skopiuj resztę kodu aplikacji bota
COPY . .

# Komenda do uruchomienia bota
CMD ["python", "bot.py"]
