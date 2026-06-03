"""
Module de collecte de restaurants via Foursquare Places API.
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

# Catégories Foursquare pour restaurants
# https://docs.foursquare.com/data-products/docs/categories
FOURSQUARE_CATEGORIES = "13065"  # Restaurants

# Mapping des catégories Foursquare vers nos types de cuisine
CUISINE_CATEGORY_MAP = {
    # Alsacien / Français
    "13068": "Alsacien",      # French Restaurant
    "13001": "Francais",      # Bistro
    "13002": "Francais",      # Brasserie
    # Italien
    "13064": "Italien",       # Italian Restaurant
    "13065": "Italien",       # Pizzeria (sous-catégorie)
    # Asiatique
    "13072": "Asiatique",     # Japanese Restaurant
    "13099": "Asiatique",     # Chinese Restaurant
    "13097": "Asiatique",     # Vietnamese Restaurant
    "13352": "Asiatique",     # Thai Restaurant
    "13303": "Asiatique",     # Sushi Restaurant
    # Gastronomique
    "13377": "Gastronomique", # Fine Dining Restaurant
}

# Mots-clés pour détecter le type de cuisine depuis le nom
CUISINE_KEYWORDS = {
    "alsacien": ["winstub", "alsace", "alsacien", "choucroute", "flammekueche", "baeckeoffe", "caveau"],
    "italien": ["italien", "pizza", "pasta", "trattoria", "ristorante", "pizzeria", "osteria"],
    "asiatique": ["asiatique", "chinois", "japonais", "vietnamien", "thai", "sushi", "wok", "asia"],
    "francais": ["français", "bistrot", "brasserie", "terroir", "traditionnel", "auberge"],
    "gastronomique": ["gastronomique", "étoilé", "gourmet"],
}


def _get_foursquare_headers() -> Dict[str, str]:
    """Retourne les headers pour l'API Foursquare (nouvelle API 2025)."""
    return {
        "Authorization": f"Bearer {config.FOURSQUARE_API_KEY}",
        "Accept": "application/json",
        "X-Places-Api-Version": "2025-06-17"
    }


def _detect_cuisine_type(name: str, categories: List[Dict]) -> str:
    """Détecte le type de cuisine depuis le nom et les catégories Foursquare."""
    name_lower = name.lower()

    # D'abord chercher dans les mots-clés du nom
    for cuisine, keywords in CUISINE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in name_lower:
                return cuisine.capitalize()

    # Ensuite chercher dans les catégories Foursquare (nouvelle API avec BSON IDs)
    # On utilise le nom de la catégorie plutôt que l'ID
    for cat in categories:
        cat_name = cat.get("name", "").lower()
        # Mapping par nom de catégorie
        if any(kw in cat_name for kw in ["french", "bistro", "brasserie"]):
            return "Francais"
        if any(kw in cat_name for kw in ["italian", "pizza", "pasta"]):
            return "Italien"
        if any(kw in cat_name for kw in ["japanese", "chinese", "vietnamese", "thai", "sushi", "asian"]):
            return "Asiatique"
        if any(kw in cat_name for kw in ["fine dining", "gourmet"]):
            return "Gastronomique"
        if any(kw in cat_name for kw in ["alsacien", "winstub"]):
            return "Alsacien"

    return "Francais"  # Défaut


def _price_level_to_string(price: Optional[int]) -> str:
    """Convertit le niveau de prix Foursquare en chaîne."""
    if price is None:
        return "N/C"
    mapping = {1: "€", 2: "€€", 3: "€€€", 4: "€€€€"}
    return mapping.get(price, "N/C")


def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance approximative en km entre deux points."""
    from math import radians, sin, cos, sqrt, atan2

    R = 6371  # Rayon de la Terre en km

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


def _fetch_restaurants_from_foursquare() -> List[Dict]:
    """Récupère les restaurants depuis Foursquare Places API (nouvelle API 2025)."""
    api_key = config.FOURSQUARE_API_KEY

    if not api_key:
        print("  ⚠ Restaurants : FOURSQUARE_API_KEY non configurée")
        return []

    # Nouvelle URL API 2025 (sans /v3/)
    url = "https://places-api.foursquare.com/places/search"

    params = {
        "ll": f"{GUEBWILLER_LAT},{GUEBWILLER_LON}",
        "radius": SEARCH_RADIUS,
        "categories": FOURSQUARE_CATEGORIES,
        "limit": 10,
        "fields": "fsq_place_id,name,location,categories,rating,price,popularity,latitude,longitude"
    }

    all_restaurants = []

    try:
        response = requests.get(url, headers=_get_foursquare_headers(), params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])

        for place in results:
            # Nouvelle API : latitude/longitude directement ou dans location
            lat = place.get("latitude") or place.get("location", {}).get("latitude", GUEBWILLER_LAT)
            lng = place.get("longitude") or place.get("location", {}).get("longitude", GUEBWILLER_LON)

            # Calculer la distance
            distance = _calculate_distance(GUEBWILLER_LAT, GUEBWILLER_LON, lat, lng)

            # Extraire la ville depuis location
            location = place.get("location", {})
            city = location.get("locality", location.get("region", ""))

            # Détecter le type de cuisine
            categories = place.get("categories", [])
            cuisine = _detect_cuisine_type(place.get("name", ""), categories)

            # Rating Foursquare est sur 10, on le convertit sur 5
            rating_10 = place.get("rating", 0)
            rating = round(rating_10 / 2, 1) if rating_10 else 0

            # Popularity comme proxy pour les avis (stats supprimé dans nouvelle API)
            popularity = place.get("popularity", 0)
            reviews_count = int(popularity * 100) if popularity > 0 else 0

            # Construire l'adresse
            address = location.get("formatted_address", location.get("address", ""))

            # URL Google Maps pour la navigation
            maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

            restaurant = {
                "title": place.get("name", "Restaurant"),
                "cuisine": cuisine,
                "city": city,
                "distance_km": round(distance, 1),
                "rating": rating,
                "reviews_count": reviews_count,
                "price_level": _price_level_to_string(place.get("price")),
                "address": address,
                "fsq_id": place.get("fsq_place_id", ""),
                "url": maps_url,
                "reason": ""
            }

            all_restaurants.append(restaurant)

    except requests.exceptions.RequestException as e:
        print(f"  ⚠ Erreur Foursquare API: {e}")
        return []

    return all_restaurants


def _score_restaurant(restaurant: Dict) -> float:
    """Calcule un score pour un restaurant."""
    score = 0.0

    # Note (0-5) -> 0-0.5
    rating = restaurant.get("rating", 0)
    score += (rating / 5) * 0.5

    # Nombre d'avis/activité (logarithmique)
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
    1. Un restaurant bien noté (>4.0, populaire)
    2. Une découverte (moins connu mais bien noté)
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
    well_rated = [r for r in available if r["rating"] >= 4.0 and r["reviews_count"] >= 50]
    well_rated.sort(key=lambda r: _score_restaurant(r), reverse=True)

    if well_rated:
        best = well_rated[0]
        best["reason"] = "Bien noté, valeur sûre"
        selected.append(best)
        used_cuisines.add(best["cuisine"].lower())
        available = [r for r in available if r["title"] != best["title"]]

    # 2. Découverte (moins connu mais bien noté)
    discoveries = [r for r in available
                   if r["rating"] >= 3.8 and r["reviews_count"] < 50 and r["reviews_count"] > 0]
    discoveries.sort(key=lambda r: r["rating"], reverse=True)

    if discoveries:
        discovery = discoveries[0]
        discovery["reason"] = "Petite perle à découvrir"
        selected.append(discovery)
        used_cuisines.add(discovery["cuisine"].lower())
        available = [r for r in available if r["title"] != discovery["title"]]

    # 3. Cuisine différente
    different_cuisine = [r for r in available
                        if r["cuisine"].lower() not in used_cuisines and r["rating"] >= 3.5]
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

    print("  Restaurants : CACHE MISS → Foursquare API")

    # Récupérer les restaurants depuis Foursquare
    all_restaurants = _fetch_restaurants_from_foursquare()

    if not all_restaurants:
        print("  ⚠ Aucun restaurant trouvé via Foursquare")
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
