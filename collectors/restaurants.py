"""
Module de collecte de restaurants via scraping.
Sources : Le Fooding, Petit Futé, Visit Alsace, TripAdvisor.
Aucune API tierce - uniquement requests + BeautifulSoup.
"""

import requests
from bs4 import BeautifulSoup
from typing import Dict, List
import re
from engine.cache import cache_get, cache_set, CACHE_TTL


# Coordonnées de Guebwiller pour calcul de distance
GUEBWILLER_LAT = 47.9069
GUEBWILLER_LON = 7.2147

# User-Agent pour éviter les blocages
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# Villes alsaciennes pour extraction
ALSACE_CITIES = [
    "Strasbourg", "Colmar", "Mulhouse", "Ribeauvillé", "Riquewihr", "Obernai",
    "Sélestat", "Haguenau", "Saverne", "Wissembourg", "Kaysersberg", "Guebwiller",
    "Thann", "Rouffach", "Soultz", "Munster", "Barr", "Molsheim", "Illkirch",
    "Schiltigheim", "Bischheim", "Lingolsheim", "Hoenheim", "Ostwald", "Illzach",
    "Wittenheim", "Kingersheim", "Rixheim", "Riedisheim", "Pfastatt", "Cernay",
    "Ensisheim", "Altkirch", "Saint-Louis", "Huningue", "Wintzenheim", "Turckheim",
    "Ammerschwihr", "Eguisheim", "Bergheim", "Marlenheim", "Wasselonne", "Brumath"
]


def _extract_city(text: str) -> str:
    """Extrait une ville alsacienne depuis un texte."""
    if not text:
        return "Alsace"
    text_lower = text.lower()
    for city in ALSACE_CITIES:
        if city.lower() in text_lower:
            return city
    return "Alsace"


def _fetch_fooding_restaurants() -> List[Dict]:
    """
    Scrape les restaurants Le Fooding en Alsace.
    Parsing amélioré pour extraire tous les restaurants.
    """
    url = "https://lefooding.com/restaurants?region=alsace"
    restaurants = []

    print(f"\n  [FOODING] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [FOODING] Status HTTP: {response.status_code}")

        if response.status_code != 200:
            print(f"  [FOODING] Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        print(f"  [FOODING] HTML (300 premiers chars):\n{response.text[:300]}\n")

        # Chercher tous les liens vers des restaurants
        all_links = soup.find_all("a", href=True)
        resto_links = [a for a in all_links if "/restaurants/" in a.get("href", "")
                       and a.get("href") != "/restaurants"
                       and not a.get("href").endswith("/restaurants/")]
        print(f"  [FOODING] Liens /restaurants/ trouvés: {len(resto_links)}")

        seen_names = set()

        for link in resto_links[:30]:
            try:
                href = link.get("href", "")
                name = link.get_text(strip=True)

                # Si le nom est vide, extraire de l'URL
                if not name or len(name) < 2:
                    match = re.search(r'/restaurants/([^/]+)', href)
                    if match:
                        name = match.group(1).replace('-', ' ').title()

                # Nettoyer le nom
                name = re.sub(r'\s+', ' ', name).strip()

                # Ignorer les noms génériques
                if not name or len(name) < 3 or name.lower() in ['restaurants', 'voir', 'plus', 'alsace', 'en savoir plus']:
                    continue

                # Éviter les doublons
                name_key = name.lower()
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)

                # Chercher la ville
                parent = link.find_parent(["article", "div", "li"])
                city = "Alsace"
                if parent:
                    parent_text = parent.get_text()
                    city = _extract_city(parent_text)

                full_url = href if href.startswith("http") else f"https://lefooding.com{href}"

                restaurants.append({
                    "title": name,
                    "city": city,
                    "cuisine": "Contemporain",
                    "source": "Le Fooding",
                    "url": full_url,
                    "reason": "Sélection Le Fooding"
                })
                print(f"  [FOODING] Trouvé: {name} ({city})")

            except Exception as e:
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [FOODING] Erreur requête: {e}")

    print(f"  [FOODING] Total: {len(restaurants)} restaurants")
    return restaurants


def _fetch_petitfute_restaurants() -> List[Dict]:
    """
    Scrape les restaurants Petit Futé en Alsace.
    """
    url = "https://www.petitfute.com/v50952-alsace/c1165-restaurants/c1179-tables-gourmandes.html"
    restaurants = []

    print(f"\n  [PETITFUTE] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [PETITFUTE] Status HTTP: {response.status_code}")
        print(f"  [PETITFUTE] HTML (300 premiers chars):\n{response.text[:300]}\n")

        if response.status_code != 200:
            print(f"  [PETITFUTE] Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Petit Futé utilise des cartes POI
        cards = soup.select(".poi-item, .listing-item, article, .node-poi, [class*='poi']")
        print(f"  [PETITFUTE] Cartes trouvées: {len(cards)}")

        # Chercher aussi les liens directs
        links = soup.select("a[href*='/v'][href*='-restaurant'], a[href*='/v'][href*='gastronomie']")
        print(f"  [PETITFUTE] Liens restaurants: {len(links)}")

        seen = set()

        # Parser les cartes
        for card in cards[:20]:
            try:
                name_el = card.select_one("h2, h3, .title, .name, .poi-title, a")
                name = name_el.get_text(strip=True) if name_el else None

                if not name or len(name) < 3 or name.lower() in seen:
                    continue
                seen.add(name.lower())

                location_el = card.select_one(".location, .city, .address, .poi-location")
                city = _extract_city(location_el.get_text() if location_el else card.get_text())

                link_el = card.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://www.petitfute.com{href}"

                restaurants.append({
                    "title": name,
                    "city": city,
                    "cuisine": "Gastronomique",
                    "source": "Petit Futé",
                    "url": full_url,
                    "reason": "Table gourmande Petit Futé"
                })
                print(f"  [PETITFUTE] Trouvé: {name} ({city})")

            except Exception:
                continue

        # Parser les liens si pas assez de cartes
        if len(restaurants) < 5:
            for link in links[:15]:
                try:
                    name = link.get_text(strip=True)
                    if not name or len(name) < 3 or name.lower() in seen:
                        continue
                    seen.add(name.lower())

                    href = link.get("href", "")
                    full_url = href if href.startswith("http") else f"https://www.petitfute.com{href}"
                    city = _extract_city(name)

                    restaurants.append({
                        "title": name,
                        "city": city,
                        "cuisine": "Gastronomique",
                        "source": "Petit Futé",
                        "url": full_url,
                        "reason": "Table gourmande Petit Futé"
                    })
                    print(f"  [PETITFUTE] Trouvé (lien): {name}")

                except Exception:
                    continue

    except requests.exceptions.RequestException as e:
        print(f"  [PETITFUTE] Erreur requête: {e}")

    print(f"  [PETITFUTE] Total: {len(restaurants)} restaurants")
    return restaurants


def _fetch_visitalsace_restaurants() -> List[Dict]:
    """
    Scrape les restaurants depuis Visit Alsace (tourisme officiel).
    """
    url = "https://www.visit.alsace/ou-manger/restaurants-gastronomiques/"
    restaurants = []

    print(f"\n  [VISITALSACE] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [VISITALSACE] Status HTTP: {response.status_code}")
        print(f"  [VISITALSACE] HTML (300 premiers chars):\n{response.text[:300]}\n")

        if response.status_code != 200:
            # Essayer URL alternative
            alt_url = "https://www.visit.alsace/gastronomie/restaurants/"
            print(f"  [VISITALSACE] Essai URL alternative: {alt_url}")
            response = requests.get(alt_url, headers=HEADERS, timeout=15)
            print(f"  [VISITALSACE] Status HTTP alt: {response.status_code}")
            if response.status_code != 200:
                return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Visit Alsace utilise des cartes SIT
        cards = soup.select("article, .card, .item, [class*='card'], [class*='result'], .sit-item")
        print(f"  [VISITALSACE] Cartes trouvées: {len(cards)}")

        seen = set()

        for card in cards[:20]:
            try:
                name_el = card.select_one("h2, h3, .title, .name, a")
                name = name_el.get_text(strip=True) if name_el else None

                if not name or len(name) < 3:
                    continue

                # Filtrer les noms génériques
                if name.lower() in ['voir plus', 'découvrir', 'restaurants', 'en savoir plus', 'alsace']:
                    continue

                if name.lower() in seen:
                    continue
                seen.add(name.lower())

                city = _extract_city(card.get_text())

                link_el = card.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://www.visit.alsace{href}"

                restaurants.append({
                    "title": name,
                    "city": city,
                    "cuisine": "Alsacien",
                    "source": "Visit Alsace",
                    "url": full_url,
                    "reason": "Recommandé par Visit Alsace"
                })
                print(f"  [VISITALSACE] Trouvé: {name} ({city})")

            except Exception:
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [VISITALSACE] Erreur requête: {e}")

    print(f"  [VISITALSACE] Total: {len(restaurants)} restaurants")
    return restaurants


def _fetch_tripadvisor_restaurants() -> List[Dict]:
    """
    Scrape les meilleurs restaurants TripAdvisor en Alsace.
    """
    url = "https://www.tripadvisor.fr/Restaurants-g187073-Alsace.html"
    restaurants = []

    print(f"\n  [TRIPADVISOR] Scraping {url}")

    try:
        ta_headers = HEADERS.copy()
        ta_headers["Referer"] = "https://www.tripadvisor.fr/"

        response = requests.get(url, headers=ta_headers, timeout=15)
        print(f"  [TRIPADVISOR] Status HTTP: {response.status_code}")
        print(f"  [TRIPADVISOR] HTML (300 premiers chars):\n{response.text[:300]}\n")

        if response.status_code != 200:
            print(f"  [TRIPADVISOR] Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Chercher les liens vers restaurants
        links = soup.select("a[href*='Restaurant_Review']")
        print(f"  [TRIPADVISOR] Liens Restaurant_Review: {len(links)}")

        seen = set()
        for link in links[:20]:
            try:
                name = link.get_text(strip=True)
                if not name or len(name) < 3 or name.lower() in seen:
                    continue

                # Filtrer les textes non-restaurant
                if any(x in name.lower() for x in ['avis', 'voir', 'photo', 'menu', 'réserver']):
                    continue

                seen.add(name.lower())
                href = link.get("href", "")
                full_url = href if href.startswith("http") else f"https://www.tripadvisor.fr{href}"

                # Extraire la ville du contexte
                parent = link.find_parent(["div", "li", "article"])
                city = "Alsace"
                if parent:
                    city = _extract_city(parent.get_text())

                restaurants.append({
                    "title": name,
                    "city": city,
                    "cuisine": "Gastronomique",
                    "source": "TripAdvisor",
                    "url": full_url,
                    "reason": "Top TripAdvisor Alsace"
                })
                print(f"  [TRIPADVISOR] Trouvé: {name} ({city})")

            except Exception:
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [TRIPADVISOR] Erreur requête: {e}")

    print(f"  [TRIPADVISOR] Total: {len(restaurants)} restaurants")
    return restaurants


def _fetch_lalsace_restaurants() -> List[Dict]:
    """
    Scrape les restaurants depuis L'Alsace/DNA (presse locale).
    Section gastronomie.
    """
    url = "https://www.lalsace.fr/magazine/gastronomie"
    restaurants = []

    print(f"\n  [LALSACE] Scraping {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  [LALSACE] Status HTTP: {response.status_code}")
        print(f"  [LALSACE] HTML (300 premiers chars):\n{response.text[:300]}\n")

        if response.status_code != 200:
            print(f"  [LALSACE] Erreur HTTP {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Chercher les articles
        articles = soup.select("article, .article, .teaser, [class*='article']")
        print(f"  [LALSACE] Articles trouvés: {len(articles)}")

        resto_keywords = ["restaurant", "table", "chef", "cuisine", "étoile", "gastronomie",
                         "winstub", "auberge", "hostellerie", "relais"]

        for article in articles[:15]:
            try:
                title_el = article.select_one("h2, h3, .title, a")
                title = title_el.get_text(strip=True) if title_el else None

                if not title or len(title) < 5:
                    continue

                # Filtrer par mots-clés restaurant
                if not any(kw in title.lower() for kw in resto_keywords):
                    continue

                link_el = article.select_one("a[href]")
                href = link_el.get("href", "") if link_el else ""
                full_url = href if href.startswith("http") else f"https://www.lalsace.fr{href}"

                city = _extract_city(title + " " + article.get_text())

                restaurants.append({
                    "title": title[:60],
                    "city": city,
                    "cuisine": "Gastronomique",
                    "source": "L'Alsace",
                    "url": full_url,
                    "reason": "Article gastronomie L'Alsace"
                })
                print(f"  [LALSACE] Trouvé: {title[:50]}...")

            except Exception:
                continue

    except requests.exceptions.RequestException as e:
        print(f"  [LALSACE] Erreur requête: {e}")

    print(f"  [LALSACE] Total: {len(restaurants)} restaurants")
    return restaurants


def _deduplicate_restaurants(restaurants: List[Dict]) -> List[Dict]:
    """Supprime les doublons par nom de restaurant (normalisation)."""
    seen = set()
    unique = []
    for r in restaurants:
        # Normaliser le nom pour comparaison
        name_normalized = re.sub(r'[^a-z0-9]', '', r["title"].lower())
        if name_normalized not in seen and len(name_normalized) > 2:
            seen.add(name_normalized)
            unique.append(r)
    return unique


def get_restaurant_suggestions(period: Dict) -> List[Dict]:
    """
    Récupère les suggestions de restaurants pour une période donnée.
    Scrape Le Fooding, Petit Futé, Visit Alsace, TripAdvisor, L'Alsace.
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

    # Scraper les sources (ordre de priorité)
    fooding = _fetch_fooding_restaurants()
    all_restaurants.extend(fooding)

    petitfute = _fetch_petitfute_restaurants()
    all_restaurants.extend(petitfute)

    visitalsace = _fetch_visitalsace_restaurants()
    all_restaurants.extend(visitalsace)

    tripadvisor = _fetch_tripadvisor_restaurants()
    all_restaurants.extend(tripadvisor)

    lalsace = _fetch_lalsace_restaurants()
    all_restaurants.extend(lalsace)

    # Dédupliquer
    all_restaurants = _deduplicate_restaurants(all_restaurants)

    print(f"\n  [TOTAL] {len(all_restaurants)} restaurants uniques trouvés")

    if not all_restaurants:
        print("  ⚠ Aucun restaurant trouvé via scraping")
        return []

    # Déduplication avec historique utilisateur
    from engine.profile import get_seen_items_normalized
    seen_restaurants = get_seen_items_normalized('restaurants', days=90)
    available = [r for r in all_restaurants if r["title"].lower() not in seen_restaurants]

    if not available:
        available = all_restaurants  # Fallback

    # Sélectionner 3 restaurants avec priorité aux sources de qualité
    selected = []
    priority_sources = ["Le Fooding", "Petit Futé", "TripAdvisor", "Visit Alsace", "L'Alsace"]

    for source in priority_sources:
        for r in available:
            if r["source"] == source and r not in selected and len(selected) < 3:
                selected.append(r)
                break

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
