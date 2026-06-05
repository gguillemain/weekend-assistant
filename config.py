import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY")
FOURSQUARE_API_KEY = os.getenv("FOURSQUARE_API_KEY")

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

# =============================================================================
# CONFIGURATION TRAVEL
# =============================================================================

# Aéroports de départ (Basel-Mulhouse)
HOME_AIRPORTS = ["BSL", "MLH"]

# Seuils de déclenchement par type de voyage (jours avant vacances)
TRAVEL_ALERT_DAYS = {
    "flight_trip": 90,      # City-breaks en avion : alerter 3 mois avant
    "roadtrip": 30,         # Roadtrips voiture : alerter 1 mois avant
    "weekend_escape": 14,   # Escapades courtes : alerter 2 semaines avant
}

# Phases de recommandation voyage
TRAVEL_PHASES = {
    "INSPIRATION": {"min_days": 90, "description": "Découvrir des destinations"},
    "OPPORTUNITIES": {"min_days": 60, "description": "Détecter les bonnes affaires"},
    "BOOKING": {"min_days": 30, "description": "Recommander la réservation"},
    "LAST_CALL": {"min_days": 0, "description": "Dernière suggestion"},
}

# Estimation prix hôtel par nuit (2 personnes, budget)
HOTEL_ESTIMATES = {
    "London": 120,
    "Dublin": 90,
    "Edinburgh": 85,
    "Budapest": 55,
    "Prague": 60,
    "Vienna": 80,
    "Amsterdam": 95,
    "Barcelona": 85,
    "Rome": 80,
    "Lisbon": 70,
    "Copenhagen": 100,
    "Madrid": 75,
    "Brussels": 80,
    "Porto": 65,
    "Seville": 70,
    "Warsaw": 50,
    "Krakow": 45,
    "Valencia": 70,
    "Milan": 85,
    "Berlin": 75,
    "default": 75,
}

HIKING_PREFS = {
    "max_elevation_gain": 300,
    "prefer_loop": True,
    "max_drive_km": 80,
    "difficulty": ["Facile", "Moyen"]
}

BIKE_PREFS = {
    "min_distance_km": 40,
    "max_distance_km": 65,
    "max_drive_km": 80,
    "allow_vtt": False,
    "allow_gravel": False,
    "prefer_cycle_paths": True,
    "max_elevation_gain": 400,       # VAE, sortie plaisir
    "max_elevation_gain_hard": 600,  # VAE, beau temps/forme
    "favorite_starts": [
        "Guebwiller", "Rouffach", "Colmar",
        "Munster", "Neuf-Brisach", "Blodelsheim",
        "Mulhouse", "Huningue", "Eguisheim",
        "Turckheim"
    ]
}

BIKE_TERRAIN_KEYWORDS = {
    "vignoble": ["vignoble", "route des vins", "coteaux", "vignes"],
    "rhin": ["rhin", "canal", "halage", "eurovelo"],
    "plaine": ["hardt", "plaine", "forêt"],
    "vallée": ["munster", "thur", "vallée"]
}

# Distances approximatives depuis Guebwiller (en km)
CITY_DISTANCES = {
    # Alsace
    "Guebwiller": 0,
    "Mulhouse": 25,
    "Colmar": 25,
    "Strasbourg": 100,
    "Wattwiller": 10,
    "Saint-Louis": 38,
    "Erstein": 58,
    "Wittelsheim": 12,
    "Rouffach": 8,
    "Munster": 20,
    "Neuf-Brisach": 30,
    "Blodelsheim": 25,
    "Huningue": 45,
    "Eguisheim": 20,
    "Turckheim": 22,
    "Cernay": 15,
    "Thann": 12,
    "Soultz-Haut-Rhin": 5,
    "Oltingue": 40,
    # Suisse
    "Bâle": 45,
    "Basel": 45,
    "Riehen": 40,
    # Allemagne - Bade-Wurtemberg
    "Freiburg": 50,
    "Breisach": 35,
    "Emmendingen": 55,
    "Offenburg": 75,
    "Lahr": 65,
    "Kehl": 90,
    "Baden-Baden": 100,
    "Lörrach": 50,
    "Weil am Rhein": 45,
    "Bad Krozingen": 45,
    # France - autres
    "Belfort": 55,
    "Besançon": 120,
    "Nancy": 150,
}
