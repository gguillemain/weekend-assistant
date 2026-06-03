"""
Module de collecte de restaurants via Google Places API.
Propose 3 suggestions de restaurants locaux avec un mix de styles.
"""

import requests
from typing import Dict, List, Optional

import config
from engine.cache import cache_get, cache_set, CACHE_TTL


# Coordonnées de Guebwiller
GUEBWILLER_LAT = 47.9069
GUEBWILLER_LON = 7.2147

# Rayon de recherche en mètres (20km)
SEARCH_RADIUS = 20000

# Types de cuisines recherchées (rotation)
CUISINE_TYPES = ["alsacien", "italien", "asiatique", "francais", "gastronomique"]

# Mapping des types Google vers nos catégories
GOOGLE_TYPE_KEYWORDS = {
    "alsacien": ["winstub", "alsace", "alsacien", "choucroute", "flammekueche", "baeckeoffe"],
    "italien": ["italien", "pizza", "pasta", "trattoria", "ristorante", "pizzeria"],
    "asiatique": ["asiatique", "chinois", "japonais", "vietnamien", "thai", "sushi", "wok"],
    "francais": ["français", "bistrot", "brasserie", "terroir", "traditionnel"],
    "gastronomique": ["gastronomique", "étoilé", "gourmet", "fine dining"],
}


def _get_google_places_url() -> str:
    """Retourne l'URL de l'API Google Places Nearby Search."""
    return "https://maps.googleapis.com/maps/api/place/nearbysearch/json"


def _detect_cuisine_type(name: str, types: List[str]) -> str:
    """Détecte le type de cuisine depuis le nom et les types Google."""
    name_lower = name.lower()

    for cuisine, keywords in GOOGLE_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in name_lower:
                return cuisine

    # Mapping des types Google
    if "meal_takeaway" in types or "meal_delivery" in types:
        return "asiatique"  # Souvent asiatique

    return "francais"  # Défaut


def _price_level_to_string(price_level: Optional[int]) -> str:
    """Convertit le niveau de prix Google en chaîne."""
    if price_level is None:
        return "N/C"
    mapping = {0: "Gratuit", 1: "€", 2: "€€", 3: "€€€", 4: "€€€€"}
    return mapping.get(price_level, "N/C")


def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance approximative en km entre deux points."""
    from math import radians, sin, cos, sqrt, atan2

    R = 6371  # Rayon de la Terre en km

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


def _fetch_restaurants_from_google() -> List[Dict]:
    """Récupère les restaurants depuis Google Places API."""
    api_key = config.GOOGLE_PLACES_API_KEY

    if not api_key:
        print("  ⚠ Restaurants : GOOGLE_PLACES_API_KEY non configurée")
        return []

    url = _get_google_places_url()

    params = {
        "location": f"{GUEBWILLER_LAT},{GUEBWILLER_LON}",
        "radius": SEARCH_RADIUS,
        "type": "restaurant",
        "key": api_key,
        "language": "fr"
    }

    all_restaurants = []

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK":
            error_msg = data.get("error_message", data.get("status", "Unknown error"))
            print(f"  ⚠ Google Places API error: {error_msg}")
            return []

        results = data.get("results", [])

        for place in results:
            # Filtrer les restaurants fermés définitivement
            if place.get("business_status") == "CLOSED_PERMANENTLY":
                continue

            # Extraire les coordonnées
            location = place.get("geometry", {}).get("location", {})
            lat = location.get("lat", GUEBWILLER_LAT)
            lng = location.get("lng", GUEBWILLER_LON)

            # Calculer la distance
            distance = _calculate_distance(GUEBWILLER_LAT, GUEBWILLER_LON, lat, lng)

            # Extraire la ville depuis l'adresse
            vicinity = place.get("vicinity", "")
            city = vicinity.split(",")[-1].strip() if "," in vicinity else vicinity

            # Détecter le type de cuisine
            cuisine = _detect_cuisine_type(place.get("name", ""), place.get("types", []))

            restaurant = {
                "title": place.get("name", "Restaurant"),
                "cuisine": cuisine.capitalize(),
                "city": city,
                "distance_km": round(distance, 1),
                "rating": place.get("rating", 0),
                "reviews_count": place.get("user_ratings_total", 0),
                "price_level": _price_level_to_string(place.get("price_level")),
                "address": vicinity,
                "place_id": place.get("place_id", ""),
                "url": f"https://www.google.com/maps/place/?q=place_id:{place.get('place_id', '')}",
                "reason": ""
            }

            all_restaurants.append(restaurant)

    except requests.exceptions.RequestException as e:
        print(f"  ⚠ Erreur Google Places API: {e}")
        return []

    return all_restaurants


def _score_restaurant(restaurant: Dict) -> float:
    """Calcule un score pour un restaurant."""
    score = 0.0

    # Note Google (0-5) -> 0-0.5
    rating = restaurant.get("rating", 0)
    score += (rating / 5) * 0.5

    # Nombre d'avis (logarithmique)
    reviews = restaurant.get("reviews_count", 0)
    if reviews > 500:
        score += 0.3
    elif reviews > 200:
        score += 0.25
    elif reviews > 100:
        score += 0.2
    elif reviews > 50:
        score += 0.15
    elif reviews > 20:
        score += 0.1

    # Proximité (bonus si proche)
    distance = restaurant.get("distance_km", 20)
    if distance < 5:
        score += 0.15
    elif distance < 10:
        score += 0.1
    elif distance < 15:
        score += 0.05

    # Pénalité si pas de note
    if rating == 0:
        score -= 0.2

    return score


def _select_mix_restaurants(restaurants: List[Dict], seen_restaurants: set) -> List[Dict]:
    """
    Sélectionne 3 restaurants avec une stratégie de mix :
    1. Un restaurant bien noté (>4.2, >100 avis)
    2. Une découverte (moins connu, <50 avis mais >4.0)
    3. Une cuisine différente des deux premiers
    """
    if not restaurants:
        return []

    selected = []
    used_cuisines = set()

    # Filtrer les restaurants déjà vus
    available = [r for r in restaurants if r["title"].lower() not in seen_restaurants]

    if not available:
        available = restaurants  # Fallback si tous ont été vus

    # 1. Restaurant bien noté
    well_rated = [r for r in available if r["rating"] >= 4.2 and r["reviews_count"] >= 100]
    well_rated.sort(key=lambda r: _score_restaurant(r), reverse=True)

    if well_rated:
        best = well_rated[0]
        best["reason"] = "Bien noté, valeur sûre"
        selected.append(best)
        used_cuisines.add(best["cuisine"].lower())
        available = [r for r in available if r["title"] != best["title"]]

    # 2. Découverte (moins connu mais bien noté)
    discoveries = [r for r in available
                   if r["rating"] >= 4.0 and r["reviews_count"] < 50 and r["reviews_count"] > 5]
    discoveries.sort(key=lambda r: r["rating"], reverse=True)

    if discoveries:
        discovery = discoveries[0]
        discovery["reason"] = "Petite perle à découvrir"
        selected.append(discovery)
        used_cuisines.add(discovery["cuisine"].lower())
        available = [r for r in available if r["title"] != discovery["title"]]

    # 3. Cuisine différente
    different_cuisine = [r for r in available
                        if r["cuisine"].lower() not in used_cuisines and r["rating"] >= 3.8]
    different_cuisine.sort(key=lambda r: _score_restaurant(r), reverse=True)

    if different_cuisine:
        diff = different_cuisine[0]
        diff["reason"] = f"Pour changer, cuisine {diff['cuisine'].lower()}"
        selected.append(diff)
    elif available:
        # Fallback : prendre le meilleur restant
        available.sort(key=lambda r: _score_restaurant(r), reverse=True)
        if available:
            fallback = available[0]
            fallback["reason"] = "Recommandé"
            selected.append(fallback)

    # Compléter si moins de 3
    remaining = [r for r in restaurants if r["title"] not in [s["title"] for s in selected]]
    remaining.sort(key=lambda r: _score_restaurant(r), reverse=True)

    while len(selected) < 3 and remaining:
        next_best = remaining.pop(0)
        next_best["reason"] = next_best.get("reason") or "Bonne adresse"
        selected.append(next_best)

    return selected[:3]


def get_restaurant_suggestions(period: Dict) -> List[Dict]:
    """
    Récupère les suggestions de restaurants pour une période donnée.

    Args:
        period: Dict avec start, end

    Returns:
        Liste de 3 restaurants suggérés
    """
    period_start = period.get("start", "")

    # Clé de cache
    cache_key = f"restaurants_{period_start}"

    # Vérifier le cache
    cached = cache_get(cache_key)
    if cached:
        print("  Restaurants : CACHE HIT")
        return cached

    print("  Restaurants : CACHE MISS → Google Places API")

    # Récupérer les restaurants depuis Google
    all_restaurants = _fetch_restaurants_from_google()

    if not all_restaurants:
        print("  ⚠ Aucun restaurant trouvé via Google Places")
        return []

    # Déduplication : récupérer les restaurants déjà visités
    from engine.profile import get_seen_items_normalized
    seen_restaurants = get_seen_items_normalized('restaurants', days=90)

    # Sélectionner le mix de 3 restaurants
    selected = _select_mix_restaurants(all_restaurants, seen_restaurants)

    print(f"  Restaurants : {len(selected)} sélectionnés sur {len(all_restaurants)} trouvés")

    # Mettre en cache
    cache_set(cache_key, selected, CACHE_TTL.get("restaurants", 480))

    return selected


def format_restaurants_context(restaurants: List[Dict]) -> str:
    """Formate les restaurants pour le contexte Claude."""
    if not restaurants:
        return "Restaurants : aucune suggestion disponible."

    lines = ["Restaurants recommandés :"]

    for i, resto in enumerate(restaurants, 1):
        rating_str = f"{resto['rating']:.1f}/5" if resto.get("rating", 0) > 0 else "N/A"
        lines.append(f"{i}. {resto['title']} ({resto['cuisine']})")
        lines.append(f"   Lieu : {resto['city']} ({resto['distance_km']} km)")
        lines.append(f"   Note : {rating_str} ({resto['reviews_count']} avis)")
        lines.append(f"   Prix : {resto['price_level']}")
        lines.append(f"   → {resto['reason']}")
        lines.append("")

    return "\n".join(lines)
