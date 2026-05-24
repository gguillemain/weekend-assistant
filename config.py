import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")

# Configuration SMTP pour l'envoi d'emails
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)
EMAIL_TO = os.getenv("EMAIL_TO") or os.getenv("SMTP_TO", "")
EMAIL_TO = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]

BASE_LOCATION = {
    "city": "Guebwiller",
    "lat": 47.9069,
    "lon": 7.2147
}

WEEKEND_RADIUS_KM = 300
VACATION_SEND_DAYS_BEFORE = 21

HIKING_PREFS = {
    "max_elevation_gain": 300,
    "prefer_loop": True,
    "max_drive_km": 80,
    "difficulty": ["Facile", "Moyen"]
}

# Distances approximatives depuis Guebwiller (en km)
CITY_DISTANCES = {
    "Guebwiller": 0,
    "Mulhouse": 25,
    "Colmar": 25,
    "Strasbourg": 100,
    "Bâle": 45,
    "Freiburg": 50,
    "Belfort": 55,
    "Besançon": 120,
    "Nancy": 150,
    "Wattwiller": 10,
    "Saint-Louis": 38,
    "Erstein": 58,
    "Riehen": 40,
    "Wittelsheim": 12,
}
