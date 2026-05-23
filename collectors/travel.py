"""
Module de suggestions de destinations voyage.
Propose des city breaks et destinations Eurotrip depuis l'Alsace.
"""

from typing import List, Dict

# City breaks accessibles en train/voiture (3-5h depuis Guebwiller)
CITY_BREAKS = [
    {
        "city": "Bâle",
        "country": "Suisse",
        "distance_km": 60,
        "transport": "voiture/train",
        "duration_h": 1,
        "highlights": ["Fondation Beyeler", "Vieille ville", "Musée Tinguely", "Art Basel"],
        "best_for": ["art", "culture", "gastronomie"],
        "budget": "€€€",
    },
    {
        "city": "Strasbourg",
        "country": "France",
        "distance_km": 100,
        "transport": "train",
        "duration_h": 1.5,
        "highlights": ["Cathédrale", "Petite France", "Musées", "Marché de Noël"],
        "best_for": ["culture", "gastronomie", "shopping"],
        "budget": "€€",
    },
    {
        "city": "Fribourg-en-Brisgau",
        "country": "Allemagne",
        "distance_km": 50,
        "transport": "voiture/train",
        "duration_h": 1,
        "highlights": ["Münster", "Bächle", "Forêt-Noire", "Marchés"],
        "best_for": ["nature", "culture", "randonnée"],
        "budget": "€€",
    },
    {
        "city": "Zurich",
        "country": "Suisse",
        "distance_km": 150,
        "transport": "train",
        "duration_h": 2.5,
        "highlights": ["Lac de Zurich", "Kunsthaus", "Vieille ville", "Bahnhofstrasse"],
        "best_for": ["art", "shopping", "gastronomie"],
        "budget": "€€€€",
    },
    {
        "city": "Lucerne",
        "country": "Suisse",
        "distance_km": 200,
        "transport": "train",
        "duration_h": 3,
        "highlights": ["Pont de la Chapelle", "Mont Pilatus", "Lac des Quatre-Cantons"],
        "best_for": ["nature", "montagne", "romantique"],
        "budget": "€€€",
    },
    {
        "city": "Stuttgart",
        "country": "Allemagne",
        "distance_km": 180,
        "transport": "train/voiture",
        "duration_h": 2.5,
        "highlights": ["Musée Mercedes", "Musée Porsche", "Staatsgalerie", "Wilhelma"],
        "best_for": ["automobile", "culture", "shopping"],
        "budget": "€€",
    },
    {
        "city": "Lyon",
        "country": "France",
        "distance_km": 400,
        "transport": "train TGV",
        "duration_h": 3.5,
        "highlights": ["Vieux Lyon", "Presqu'île", "Bouchons lyonnais", "Confluence"],
        "best_for": ["gastronomie", "culture", "architecture"],
        "budget": "€€",
    },
    {
        "city": "Paris",
        "country": "France",
        "distance_km": 500,
        "transport": "train TGV",
        "duration_h": 2.5,
        "highlights": ["Musées", "Expos temporaires", "Théâtre", "Gastronomie"],
        "best_for": ["culture", "art", "gastronomie", "shopping"],
        "budget": "€€€",
    },
    {
        "city": "Heidelberg",
        "country": "Allemagne",
        "distance_km": 120,
        "transport": "voiture/train",
        "duration_h": 1.5,
        "highlights": ["Château", "Vieille ville", "Philosophenweg", "Université"],
        "best_for": ["romantique", "culture", "histoire"],
        "budget": "€€",
    },
    {
        "city": "Berne",
        "country": "Suisse",
        "distance_km": 180,
        "transport": "train",
        "duration_h": 2.5,
        "highlights": ["Vieille ville UNESCO", "Fosse aux ours", "Zentrum Paul Klee"],
        "best_for": ["culture", "histoire", "art"],
        "budget": "€€€",
    },
]

# Destinations Eurotrip (avion ou train longue distance)
EUROTRIP_DESTINATIONS = [
    {
        "city": "Amsterdam",
        "country": "Pays-Bas",
        "transport": "train/avion",
        "duration_h": 6,
        "min_days": 3,
        "highlights": ["Rijksmuseum", "Van Gogh", "Canaux", "Jordaan"],
        "best_for": ["art", "culture", "vélo"],
        "budget": "€€€",
    },
    {
        "city": "Barcelone",
        "country": "Espagne",
        "transport": "avion",
        "duration_h": 2,
        "min_days": 4,
        "highlights": ["Sagrada Familia", "Parc Güell", "Barri Gòtic", "Plages"],
        "best_for": ["architecture", "plage", "gastronomie", "vie nocturne"],
        "budget": "€€",
    },
    {
        "city": "Rome",
        "country": "Italie",
        "transport": "avion",
        "duration_h": 2,
        "min_days": 4,
        "highlights": ["Colisée", "Vatican", "Trastevere", "Cuisine italienne"],
        "best_for": ["histoire", "art", "gastronomie"],
        "budget": "€€",
    },
    {
        "city": "Lisbonne",
        "country": "Portugal",
        "transport": "avion",
        "duration_h": 2.5,
        "min_days": 4,
        "highlights": ["Alfama", "Belém", "Tram 28", "Sintra"],
        "best_for": ["culture", "gastronomie", "photogénie"],
        "budget": "€",
    },
    {
        "city": "Vienne",
        "country": "Autriche",
        "transport": "train/avion",
        "duration_h": 7,
        "min_days": 3,
        "highlights": ["Schönbrunn", "Kunsthistorisches", "Opéra", "Cafés viennois"],
        "best_for": ["musique", "art", "architecture", "café"],
        "budget": "€€",
    },
    {
        "city": "Prague",
        "country": "Tchéquie",
        "transport": "train/avion",
        "duration_h": 6,
        "min_days": 3,
        "highlights": ["Château", "Pont Charles", "Vieille ville", "Bière"],
        "best_for": ["histoire", "architecture", "vie nocturne"],
        "budget": "€",
    },
    {
        "city": "Copenhague",
        "country": "Danemark",
        "transport": "avion",
        "duration_h": 2,
        "min_days": 3,
        "highlights": ["Nyhavn", "Tivoli", "Design danois", "Gastronomie nordique"],
        "best_for": ["design", "gastronomie", "vélo", "hygge"],
        "budget": "€€€",
    },
    {
        "city": "Édimbourg",
        "country": "Écosse",
        "transport": "avion",
        "duration_h": 2,
        "min_days": 4,
        "highlights": ["Royal Mile", "Arthur's Seat", "Whisky", "Highlands"],
        "best_for": ["histoire", "nature", "whisky"],
        "budget": "€€",
    },
    {
        "city": "Florence",
        "country": "Italie",
        "transport": "avion/train",
        "duration_h": 6,
        "min_days": 3,
        "highlights": ["Uffizi", "Duomo", "Ponte Vecchio", "Toscane"],
        "best_for": ["art", "architecture", "gastronomie"],
        "budget": "€€",
    },
    {
        "city": "Séville",
        "country": "Espagne",
        "transport": "avion",
        "duration_h": 2.5,
        "min_days": 4,
        "highlights": ["Alcázar", "Cathédrale", "Flamenco", "Tapas"],
        "best_for": ["culture", "gastronomie", "flamenco"],
        "budget": "€",
    },
]


def get_travel_suggestions(period: dict) -> Dict[str, List[Dict]]:
    """
    Retourne des suggestions de voyage adaptées à la période.

    Args:
        period: Dict avec start, end, days, mode

    Returns:
        Dict avec city_breaks et eurotrip_destinations
    """
    duration = period.get("days", 2)

    # City breaks pour les courtes périodes (2-4 jours)
    city_breaks = []
    if duration >= 2:
        # Trier par distance pour les courts séjours
        sorted_cities = sorted(CITY_BREAKS, key=lambda x: x["distance_km"])
        city_breaks = sorted_cities[:5]

    # Eurotrip pour les longues périodes (5+ jours)
    eurotrip = []
    if duration >= 5:
        # Filtrer par durée minimum
        suitable = [d for d in EUROTRIP_DESTINATIONS if d["min_days"] <= duration]
        eurotrip = suitable[:5]

    return {
        "city_breaks": city_breaks,
        "eurotrip": eurotrip,
        "duration_days": duration
    }


def format_travel_context(travel_data: Dict) -> str:
    """Formate les données voyage pour le contexte Claude."""
    lines = []

    if travel_data.get("city_breaks"):
        lines.append("CITY BREAKS (courts séjours, train/voiture) :")
        for dest in travel_data["city_breaks"]:
            highlights = ", ".join(dest["highlights"][:3])
            lines.append(f"- {dest['city']} ({dest['country']}) : {dest['duration_h']}h, {highlights}")
        lines.append("")

    if travel_data.get("eurotrip"):
        lines.append("DESTINATIONS EUROTRIP (avion, séjours plus longs) :")
        for dest in travel_data["eurotrip"]:
            highlights = ", ".join(dest["highlights"][:3])
            lines.append(f"- {dest['city']} ({dest['country']}) : min {dest['min_days']} jours, {highlights}")
        lines.append("")

    return "\n".join(lines) if lines else "Aucune destination disponible."
