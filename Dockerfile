FROM python:3.11-slim

WORKDIR /app

# Dépendances système pour lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copier requirements et installer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copier le code source
COPY . .

# Créer le dossier data pour SQLite
RUN mkdir -p /app/data

# Port exposé
EXPOSE 5000

# Variables d'environnement par défaut
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Lancement avec gunicorn (optimisé pour les appels API parallèles)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "4", "--timeout", "120", "--keep-alive", "5", "app:app"]
