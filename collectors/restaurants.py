"""
Module de collecte de restaurants — Liste statique Michelin/Gault&Millau.
Mise à jour annuelle (mars) basée sur les guides officiels.
Aucun scraping, aucune API — données fiables et stables.
"""

from typing import Dict, List
import config
from engine.cache import cache_get, cache_set, CACHE_TTL


# =============================================================================
# LISTE STATIQUE — MISE À JOUR ANNUELLE (MARS 2026)
# =============================================================================

BIB_GOURMAND_ALSACE = [
    # -------------------------------------------------------------------------
    # Haut-Rhin — proches de Guebwiller
    # -------------------------------------------------------------------------
    {
        "name": "L'AO – L'Aigle d'Or",
        "city": "Rimbach-près-Guebwiller",
        "cuisine": "alsacienne",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/rimbach-pres-guebwiller/restaurant/l-ao-l-aigle-d-or"
    },
    {
        "name": "L'Arbre Vert",
        "city": "Bernwiller",
        "cuisine": "alsacienne",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/bernwiller/restaurant/l-arbre-vert"
    },
    {
        "name": "Perle des Vosges",
        "city": "Muhlbach-sur-Munster",
        "cuisine": "régionale",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/muhlbach-sur-munster/restaurant/perle-des-vosges"
    },
    {
        "name": "La Taverne Alsacienne",
        "city": "Ingersheim",
        "cuisine": "alsacienne",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/ingersheim/restaurant/la-taverne-alsacienne"
    },
    {
        "name": "La Vieille Forge",
        "city": "Kaysersberg",
        "cuisine": "alsacienne",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/kaysersberg-vignoble/restaurant/la-vieille-forge"
    },
    {
        "name": "Winstub du Chambard",
        "city": "Kaysersberg",
        "cuisine": "winstub",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/kaysersberg-vignoble/restaurant/winstub-du-chambard"
    },
    {
        "name": "La Rochette",
        "city": "Labaroche",
        "cuisine": "régionale",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/labaroche/restaurant/la-rochette"
    },
    {
        "name": "Les Grands Arbres – Verte Vallée",
        "city": "Munster",
        "cuisine": "gastronomique",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/munster/restaurant/les-grands-arbres-verte-vallee"
    },
    {
        "name": "L'Olivier",
        "city": "Munster",
        "cuisine": "bistronomique",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/munster/restaurant/l-olivier"
    },
    {
        "name": "Au Relais des Ménétriers",
        "city": "Ribeauvillé",
        "cuisine": "alsacienne",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/ribeauville/restaurant/au-relais-des-menetriers"
    },
    {
        "name": "Le Pressoir de Bacchus",
        "city": "Blienschwiller",
        "cuisine": "alsacienne",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/blienschwiller/restaurant/le-pressoir-de-bacchus"
    },
    {
        "name": "Winstub A Côté",
        "city": "Sierentz",
        "cuisine": "winstub",
        "price": "€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/sierentz/restaurant/winstub-a-cote"
    },
    {
        "name": "Au Lion d'Or – chez Théo",
        "city": "Rosenau",
        "cuisine": "alsacienne",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/rosenau/restaurant/au-lion-d-or-chez-theo"
    },

    # -------------------------------------------------------------------------
    # Colmar
    # -------------------------------------------------------------------------
    {
        "name": "L'Atelier du Peintre",
        "city": "Colmar",
        "cuisine": "gastronomique",
        "price": "€€€",
        "distinction": "1 étoile Michelin",
        "url": "https://guide.michelin.com/fr/fr/alsace/colmar/restaurant/l-atelier-du-peintre"
    },
    {
        "name": "Wistub Brenner",
        "city": "Colmar",
        "cuisine": "winstub",
        "price": "€€",
        "distinction": "recommandé",
        "url": "https://www.wistub-brenner.fr"
    },

    # -------------------------------------------------------------------------
    # Mulhouse
    # -------------------------------------------------------------------------
    {
        "name": "Le Gavroche",
        "city": "Mulhouse",
        "cuisine": "bistronomique",
        "price": "€€",
        "distinction": "recommandé",
        "url": "https://www.restaurant-gavroche-mulhouse.fr"
    },

    # -------------------------------------------------------------------------
    # Strasbourg
    # -------------------------------------------------------------------------
    {
        "name": "Chez Yvonne – S'Burjerstuewel",
        "city": "Strasbourg",
        "cuisine": "winstub",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/strasbourg/restaurant/chez-yvonne-s-burjerstuewel"
    },
    {
        "name": "Au Pont du Corbeau",
        "city": "Strasbourg",
        "cuisine": "alsacienne",
        "price": "€€",
        "distinction": "Bib Gourmand",
        "url": "https://guide.michelin.com/fr/fr/alsace/strasbourg/restaurant/au-pont-du-corbeau"
    },

    # -------------------------------------------------------------------------
    # Bâle (Suisse)
    # -------------------------------------------------------------------------
    {
        "name": "Kunsthalle Restaurant",
        "city": "Bâle",
        "cuisine": "bistronomique",
        "price": "€€",
        "distinction": "recommandé",
        "url": "https://www.kunsthallebasel.ch/restaurant"
    },
    {
        "name": "Chez Donati",
        "city": "Bâle",
        "cuisine": "italienne",
        "price": "€€€",
        "distinction": "recommandé Gault&Millau",
        "url": "https://www.donati.ch"
    },
]


# =============================================================================
# DISTANCES DEPUIS GUEBWILLER (en km)
# Complète config.CITY_DISTANCES pour les petites communes
# =============================================================================

RESTAURANT_DISTANCES = {
    # Proches de Guebwiller (< 20km)
    "Rimbach-près-Guebwiller": 5,
    "Bernwiller": 12,
    "Muhlbach-sur-Munster": 18,
    "Ingersheim": 22,
    "Kaysersberg": 28,
    "Labaroche": 35,
    "Munster": 20,
    "Ribeauvillé": 35,
    "Blienschwiller": 45,
    "Sierentz": 30,
    "Rosenau": 42,
    # Villes principales
    "Colmar": 25,
    "Mulhouse": 25,
    "Strasbourg": 100,
    "Bâle": 45,
    "Basel": 45,
}


def _get_distance(city: str) -> int:
    """Retourne la distance depuis Guebwiller."""
    # D'abord chercher dans notre liste locale
    if city in RESTAURANT_DISTANCES:
        return RESTAURANT_DISTANCES[city]
    # Sinon dans config.CITY_DISTANCES
    if hasattr(config, 'CITY_DISTANCES') and city in config.CITY_DISTANCES:
        return config.CITY_DISTANCES[city]
    # Défaut
    return 50


def _calculate_value_score(restaurant: Dict) -> float:
    """
    Calcule le score de valeur d'un restaurant.
    Plus le score est élevé, plus le restaurant est recommandé.
    """
    score = 0.0

    # Distinction
    distinction = restaurant.get("distinction", "").lower()
    if "bib gourmand" in distinction:
        score += 0.4
    elif "étoile" in distinction or "etoile" in distinction:
        score += 0.3
    elif "recommandé" in distinction or "recommande" in distinction:
        score += 0.2

    # Prix (bon rapport qualité/prix)
    price = restaurant.get("price", "€€")
    if price == "€":
        score += 0.2
    elif price == "€€":
        score += 0.1

    # Distance (proximité favorisée)
    distance = restaurant.get("distance_km", 50)
    if distance < 15:
        score += 0.3
    elif distance < 30:
        score += 0.2
    elif distance < 50:
        score += 0.1

    # Cuisine (winstub et alsacienne favorisées)
    cuisine = restaurant.get("cuisine", "").lower()
    if cuisine in ["winstub", "alsacienne"]:
        score += 0.1

    return round(score, 2)


def _calculate_profile_match(restaurant: Dict, profile: Dict) -> float:
    """
    Calcule la correspondance avec le profil utilisateur.
    Pour l'instant, retourne 0.5 par défaut.
    Sera affiné avec le feedback utilisateur.
    """
    # TODO: Affiner avec les préférences gastronomiques du profil
    # - cuisines préférées
    # - gamme de prix
    # - types de sorties (winstub vs gastro)
    return 0.5


def get_restaurants(period: Dict, profile: Dict = None) -> List[Dict]:
    """
    Retourne la liste des restaurants triée par value_score.

    Args:
        period: Période (pour le cache)
        profile: Profil utilisateur (optionnel)

    Returns:
        Liste de restaurants avec scores calculés
    """
    if profile is None:
        profile = {}

    # Construire la liste avec scores
    restaurants = []

    for resto in BIB_GOURMAND_ALSACE:
        distance = _get_distance(resto["city"])

        restaurant = {
            "title": resto["name"],
            "city": resto["city"],
            "cuisine": resto["cuisine"],
            "price_level": resto["price"],
            "distinction": resto["distinction"],
            "url": resto["url"],
            "distance_km": distance,
            "source": "Guide Michelin",
        }

        # Calculer les scores
        restaurant["value_score"] = _calculate_value_score(restaurant)
        restaurant["profile_match"] = _calculate_profile_match(restaurant, profile)

        # Raison de la recommandation
        if "Bib Gourmand" in resto["distinction"]:
            restaurant["reason"] = f"Bib Gourmand — {resto['cuisine']} à {distance}km"
        elif "étoile" in resto["distinction"]:
            restaurant["reason"] = f"⭐ {resto['distinction']} — {resto['cuisine']}"
        else:
            restaurant["reason"] = f"{resto['distinction']} — {resto['cuisine']}"

        restaurants.append(restaurant)

    # Trier par value_score décroissant
    restaurants.sort(key=lambda r: r["value_score"], reverse=True)

    # Afficher le top 5 pour debug
    print("\n  [RESTAURANTS] Top 5 par value_score :")
    for i, r in enumerate(restaurants[:5], 1):
        print(f"    {i}. {r['title']} ({r['city']}) — {r['distance_km']}km — {r['distinction']} — score={r['value_score']}")

    # Vérifier que L'Aigle d'Or apparaît bien en tête
    if restaurants and "Aigle d'Or" in restaurants[0]["title"]:
        print("  ✓ L'Aigle d'Or (Rimbach) en tête comme attendu")
    else:
        print(f"  ⚠ Premier résultat: {restaurants[0]['title'] if restaurants else 'aucun'}")

    return restaurants


def get_restaurant_suggestions(period: Dict, profile: Dict = None) -> List[Dict]:
    """
    Récupère les suggestions de restaurants pour une période donnée.
    Wrapper pour compatibilité avec le reste du code.
    """
    period_start = period.get("start", "")
    cache_key = f"restaurants_{period_start}"

    # Vérifier le cache
    cached = cache_get(cache_key)
    if cached:
        print("  Restaurants : CACHE HIT")
        return cached

    print("  Restaurants : liste Michelin/Gault&Millau")

    # Récupérer tous les restaurants avec scores
    all_restaurants = get_restaurants(period, profile)

    if not all_restaurants:
        print("  ⚠ Aucun restaurant dans la liste")
        return []

    # Déduplication avec historique utilisateur
    from engine.profile import get_seen_items_normalized
    seen_restaurants = get_seen_items_normalized('restaurants', days=90)
    available = [r for r in all_restaurants if r["title"].lower() not in seen_restaurants]

    if not available:
        available = all_restaurants  # Fallback si tous vus

    # Sélectionner les 3 meilleurs
    selected = available[:3]

    print(f"  Restaurants : {len(selected)} sélectionnés sur {len(all_restaurants)} disponibles")

    # Ajouter champs pour compatibilité template
    for r in selected:
        r.setdefault("rating", 0)
        r.setdefault("reviews_count", 0)

    # Mettre en cache
    cache_set(cache_key, selected, CACHE_TTL.get("restaurants", 480))

    return selected


def format_restaurants_context(restaurants: List[Dict]) -> str:
    """Formate les restaurants pour le contexte Claude."""
    if not restaurants:
        return "Restaurants : aucune suggestion disponible."

    lines = ["Restaurants recommandés (sélection Michelin/Gault&Millau) :"]

    for resto in restaurants:
        lines.append(f"- {resto['title']} — {resto['city']} ({resto['distance_km']}km)")
        lines.append(f"  {resto['distinction']} | {resto['cuisine']} | {resto['price_level']}")

    return "\n".join(lines)
