"""
Module de collecte de restaurants via scraping.
Sources : Guide Michelin Bib Gourmand, Le Fooding, Gault & Millau.
Aucune API tierce - uniquement requests + BeautifulSoup.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, List
from engine.cache import cache_get, cache_set, CACHE_TTL


# Coordonnées de Guebwiller pour calcul de distance
GUEBWILLER_LAT = 47.9069
GUEBWILLER_LON = 7.2147

# User-Agent pour éviter les blocages
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def _fetch_michelin_restaurants() -> List[Dict]:
    """
    Scrape les restaurants Bib Gourmand du Guide Michelin en Alsace.
    """
    url = "https://guide.michelin.com/fr/fr/alsace/restaurants?distinctions=bib-gourmand"
    restaurants = []

    print(f"\n  [MICHELIN] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [MICHELIN] Status HTTP: {response.status_code}")
        print(f"  [MICHELIN] HTML (500 premiers chars):\n{response.text[:500]}\n")

        if response.status_code != 200:
            print(f"  [MICHELIN] Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Chercher les cartes de restaurants
        # Structure typique Michelin : div avec classe contenant "card" ou "restaurant"
        cards = soup.select("div.card__menu, div.js-restaurant-card, article.card")
        print(f"  [MICHELIN] Balises trouvées (card__menu/js-restaurant-card/article.card): {len(cards)}")

        if not cards:
            # Essayer d'autres sélecteurs
            cards = soup.select("[data-restaurant], .restaurant-item, .poi-card")
            print(f"  [MICHELIN] Balises alternatives (data-restaurant/restaurant-item/poi-card): {len(cards)}")

        if not cards:
            # Afficher les classes disponibles pour debug
            all_divs = soup.find_all("div", class_=True)[:10]
            print(f"  [MICHELIN] Exemples de classes div: {[' '.join(d.get('class', [])) for d in all_divs]}")

        for card in cards[:10]:  # Limiter à 10
            try:
                # Extraire le nom
                name_el = card.select_one("h2, h3, .card__menu-content--title, .restaurant-name, a.link")
                name = name_el.get_text(strip=True) if name_el else "Restaurant"

                # Extraire la ville/adresse
                location_el = card.select_one(".card__menu-footer--location, .location, .city, address")
                city = location_el.get_text(strip=True) if location_el else "Alsace"

                # Extraire le lien
                link_el = card.select_one("a[href*='restaurant']") or card.find("a")
                link = link_el.get("href", "") if link_el else ""
                if link and not link.startswith("http"):
                    link = f"https://guide.michelin.com{link}"

                if name and name != "Restaurant":
                    restaurants.append({
                        "title": name,
                        "city": city,
                        "cuisine": "Bib Gourmand",
                        "source": "Michelin",
                        "url": link,
                        "reason": "Bib Gourmand - Bon rapport qualité/prix"
                    })
                    print(f"  [MICHELIN] Trouvé: {name} ({city})")

            except Exception as e:
                print(f"  [MICHELIN] Erreur parsing carte: {e}")
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [MICHELIN] Erreur requête: {e}")

    print(f"  [MICHELIN] Total: {len(restaurants)} restaurants")
    return restaurants


def _fetch_fooding_restaurants() -> List[Dict]:
    """
    Scrape les restaurants Le Fooding en Alsace.
    """
    url = "https://lefooding.com/restaurants?region=alsace"
    restaurants = []

    print(f"\n  [FOODING] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [FOODING] Status HTTP: {response.status_code}")
        print(f"  [FOODING] HTML (300 premiers chars):\n{response.text[:300]}\n")

        if response.status_code != 200:
            print(f"  [FOODING] Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Chercher les cartes de restaurants
        cards = soup.select("article.card, div.restaurant-card, .resto-item, [data-restaurant]")
        print(f"  [FOODING] Balises trouvées (article.card/restaurant-card/resto-item): {len(cards)}")

        if not cards:
            # Essayer d'autres sélecteurs
            cards = soup.select("a[href*='/restaurant/'], div.card, article")
            print(f"  [FOODING] Balises alternatives: {len(cards)}")

        if not cards:
            # Afficher les classes disponibles pour debug
            all_articles = soup.find_all("article", class_=True)[:5]
            all_divs = soup.find_all("div", class_=True)[:10]
            print(f"  [FOODING] Exemples articles: {[' '.join(a.get('class', [])) for a in all_articles]}")
            print(f"  [FOODING] Exemples divs: {[' '.join(d.get('class', [])) for d in all_divs]}")

        for card in cards[:10]:
            try:
                name_el = card.select_one("h2, h3, .title, .name, .card-title")
                name = name_el.get_text(strip=True) if name_el else None

                location_el = card.select_one(".location, .city, .address, .place")
                city = location_el.get_text(strip=True) if location_el else "Alsace"

                link_el = card.select_one("a[href*='restaurant']") or card.find("a")
                link = link_el.get("href", "") if link_el else ""
                if link and not link.startswith("http"):
                    link = f"https://lefooding.com{link}"

                if name:
                    restaurants.append({
                        "title": name,
                        "city": city,
                        "cuisine": "Contemporain",
                        "source": "Le Fooding",
                        "url": link,
                        "reason": "Sélection Le Fooding"
                    })
                    print(f"  [FOODING] Trouvé: {name} ({city})")

            except Exception as e:
                print(f"  [FOODING] Erreur parsing: {e}")
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [FOODING] Erreur requête: {e}")

    print(f"  [FOODING] Total: {len(restaurants)} restaurants")
    return restaurants


def _fetch_gaultmillau_restaurants() -> List[Dict]:
    """
    Scrape les restaurants Gault & Millau en Alsace.
    """
    url = "https://www.gaultmillau.fr/restaurants/alsace"
    restaurants = []

    print(f"\n  [GAULT&MILLAU] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [GAULT&MILLAU] Status HTTP: {response.status_code}")
        print(f"  [GAULT&MILLAU] HTML (300 premiers chars):\n{response.text[:300]}\n")

        if response.status_code != 200:
            print(f"  [GAULT&MILLAU] Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Chercher les cartes de restaurants
        cards = soup.select("article.card, div.restaurant-card, .restaurant-item, [data-restaurant]")
        print(f"  [GAULT&MILLAU] Balises trouvées: {len(cards)}")

        if not cards:
            cards = soup.select("a[href*='/restaurant'], div.card, article, .item")
            print(f"  [GAULT&MILLAU] Balises alternatives: {len(cards)}")

        if not cards:
            all_articles = soup.find_all("article")[:5]
            all_divs = soup.find_all("div", class_=True)[:10]
            print(f"  [GAULT&MILLAU] Exemples articles: {[a.get('class', []) for a in all_articles]}")
            print(f"  [GAULT&MILLAU] Exemples divs: {[' '.join(d.get('class', [])) for d in all_divs]}")

        for card in cards[:10]:
            try:
                name_el = card.select_one("h2, h3, .title, .name, .restaurant-name")
                name = name_el.get_text(strip=True) if name_el else None

                location_el = card.select_one(".location, .city, .address")
                city = location_el.get_text(strip=True) if location_el else "Alsace"

                # Score Gault & Millau
                score_el = card.select_one(".score, .rating, .note, .points")
                score = score_el.get_text(strip=True) if score_el else ""

                link_el = card.select_one("a[href*='restaurant']") or card.find("a")
                link = link_el.get("href", "") if link_el else ""
                if link and not link.startswith("http"):
                    link = f"https://www.gaultmillau.fr{link}"

                if name:
                    reason = f"Gault & Millau {score}" if score else "Sélection Gault & Millau"
                    restaurants.append({
                        "title": name,
                        "city": city,
                        "cuisine": "Gastronomique",
                        "source": "Gault & Millau",
                        "url": link,
                        "reason": reason
                    })
                    print(f"  [GAULT&MILLAU] Trouvé: {name} ({city}) {score}")

            except Exception as e:
                print(f"  [GAULT&MILLAU] Erreur parsing: {e}")
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [GAULT&MILLAU] Erreur requête: {e}")

    print(f"  [GAULT&MILLAU] Total: {len(restaurants)} restaurants")
    return restaurants


def _deduplicate_restaurants(restaurants: List[Dict]) -> List[Dict]:
    """Supprime les doublons par nom de restaurant."""
    seen = set()
    unique = []
    for r in restaurants:
        name_lower = r["title"].lower().strip()
        if name_lower not in seen:
            seen.add(name_lower)
            unique.append(r)
    return unique


def get_restaurant_suggestions(period: Dict) -> List[Dict]:
    """
    Récupère les suggestions de restaurants pour une période donnée.
    Scrape Michelin, Le Fooding et Gault & Millau.
    """
    period_start = period.get("start", "")
    cache_key = f"restaurants_{period_start}"

    # Vérifier le cache
    cached = cache_get(cache_key)
    if cached:
        print("  Restaurants : CACHE HIT")
        return cached

    print("  Restaurants : CACHE MISS → scraping guides gastronomiques")

    all_restaurants = []

    # Scraper les 3 sources
    michelin = _fetch_michelin_restaurants()
    all_restaurants.extend(michelin)

    fooding = _fetch_fooding_restaurants()
    all_restaurants.extend(fooding)

    gaultmillau = _fetch_gaultmillau_restaurants()
    all_restaurants.extend(gaultmillau)

    # Dédupliquer
    all_restaurants = _deduplicate_restaurants(all_restaurants)

    if not all_restaurants:
        print("  ⚠ Aucun restaurant trouvé via scraping")
        return []

    # Déduplication avec historique utilisateur
    from engine.profile import get_seen_items_normalized
    seen_restaurants = get_seen_items_normalized('restaurants', days=90)
    available = [r for r in all_restaurants if r["title"].lower() not in seen_restaurants]

    if not available:
        available = all_restaurants  # Fallback

    # Sélectionner 3 restaurants (un de chaque source si possible)
    selected = []
    sources_used = set()

    for r in available:
        if r["source"] not in sources_used and len(selected) < 3:
            selected.append(r)
            sources_used.add(r["source"])

    # Compléter si moins de 3
    for r in available:
        if r not in selected and len(selected) < 3:
            selected.append(r)

    print(f"  Restaurants : {len(selected)} sélectionnés sur {len(all_restaurants)} trouvés")

    # Ajouter les champs manquants pour compatibilité template
    for r in selected:
        r.setdefault("distance_km", 0)
        r.setdefault("rating", 0)
        r.setdefault("reviews_count", 0)
        r.setdefault("price_level", "€€€")

    # Mettre en cache
    cache_set(cache_key, selected, CACHE_TTL.get("restaurants", 480))

    return selected


def format_restaurants_context(restaurants: List[Dict]) -> str:
    """Formate les restaurants pour le contexte Claude."""
    if not restaurants:
        return "Restaurants : aucune suggestion disponible."

    lines = ["Restaurants recommandés (guides gastronomiques) :"]

    for i, resto in enumerate(restaurants, 1):
        lines.append(f"{i}. {resto['title']} ({resto.get('cuisine', 'Gastronomique')})")
        lines.append(f"   Lieu : {resto.get('city', 'Alsace')}")
        lines.append(f"   Source : {resto.get('source', 'Guide')}")
        lines.append(f"   → {resto.get('reason', 'Recommandé')}")
        lines.append("")

    return "\n".join(lines)
