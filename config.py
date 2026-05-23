import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")

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
