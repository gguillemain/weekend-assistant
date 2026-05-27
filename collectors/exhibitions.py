"""
Module de collecte des expositions via scraping des fondations et musées locaux.
"""

import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import re

import config
from engine.cache import cache_get, cache_set, CACHE_TTL

# Distances depuis Guebwiller
CITY_DISTANCES = getattr(config, "CITY_DISTANCES", {})

# Headers pour le scraping
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Mots-clés pour détecter le style
STYLE_KEYWORDS = {
    "contemporain": ["contemporain", "contemporary", "moderne", "modern", "actuel"],
    "surréaliste": ["surréaliste", "surrealist", "surréalisme", "onirique", "fantastique"],
    "street art": ["street art", "street-art", "graffiti", "urbain", "urban art", "banksy"],
}


def _get_distance(city: str) -> float:
    """Retourne la distance depuis Guebwiller pour une ville."""
    city_lower = city.lower().strip()
    for known_city, dist in CITY_DISTANCES.items():
        if known_city.lower() in city_lower or city_lower in known_city.lower():
            return float(dist)
    return 100.0  # Distance par défaut si ville inconnue


def _parse_date_fr(text: str) -> Optional[date]:
    """Parse une date française (ex: '15 mars 2026', '15/03/2026')."""
    if not text:
        return None

    text = text.strip().lower()

    # Mois français
    months_fr = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
        "jan": 1, "fév": 2, "mar": 3, "avr": 4, "jui": 6, "jul": 7,
        "aoû": 8, "sep": 9, "oct": 10, "nov": 11, "déc": 12
    }

    # Format "15 mars 2026" ou "15 mars"
    match = re.search(r"(\d{1,2})\s+([a-zéû]+)\.?\s*(\d{4})?", text)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        year = int(match.group(3)) if match.group(3) else date.today().year

        for month_name, month_num in months_fr.items():
            if month_str.startswith(month_name[:3]):
                try:
                    return date(year, month_num, day)
                except ValueError:
                    pass

    # Format "15/03/2026" ou "15.03.2026"
    match = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", text)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            pass

    return None


def _extract_dates(text: str) -> tuple:
    """Extrait les dates de début et fin d'une chaîne."""
    if not text:
        return None, None

    # Patterns courants
    # "Du 15 mars au 30 juin 2026"
    # "15.03 - 30.06.2026"
    # "Jusqu'au 30 juin 2026"

    text_clean = text.lower().strip()

    # Pattern "du X au Y"
    match = re.search(r"du\s+(.+?)\s+au\s+(.+?)(?:\s*$|\s*[-–])", text_clean)
    if match:
        start = _parse_date_fr(match.group(1))
        end = _parse_date_fr(match.group(2))
        if start and end:
            return start, end

    # Pattern avec tiret ou flèche
    parts = re.split(r"\s*[-–→]\s*", text_clean)
    if len(parts) >= 2:
        start = _parse_date_fr(parts[0])
        end = _parse_date_fr(parts[-1])
        if start or end:
            return start, end

    # "Jusqu'au X"
    match = re.search(r"jusqu[''']?\s*au\s+(.+)", text_clean)
    if match:
        end = _parse_date_fr(match.group(1))
        if end:
            return None, end

    # Une seule date
    single_date = _parse_date_fr(text)
    if single_date:
        return single_date, single_date

    return None, None


def _calculate_profile_match(
    title: str,
    artists: List[str],
    description: str,
    venue: str,
    profile: Dict
) -> float:
    """
    Calcule le score de correspondance avec le profil.

    Args:
        title: Titre de l'expo
        artists: Liste des artistes
        description: Description
        venue: Nom du lieu
        profile: Profil utilisateur

    Returns:
        Score entre 0 et 1
    """
    score = 0.0

    title_lower = title.lower() if title else ""
    desc_lower = description.lower() if description else ""
    venue_lower = venue.lower() if venue else ""
    all_text = f"{title_lower} {desc_lower}"

    # Match artiste favori (+0.5)
    favorite_artists = profile.get("expo_artists", [])
    for fav in favorite_artists:
        fav_lower = fav.lower()
        # Vérifier dans le titre, description et liste artistes
        if fav_lower in all_text:
            score += 0.5
            break
        for artist in artists:
            if fav_lower in artist.lower() or artist.lower() in fav_lower:
                score += 0.5
                break
        if score >= 0.5:
            break

    # Match style (+0.2)
    expo_style = profile.get("expo_style", "").lower()
    for style_name, keywords in STYLE_KEYWORDS.items():
        if style_name in expo_style:
            for kw in keywords:
                if kw in all_text:
                    score += 0.2
                    break
            break

    # Match fondation favorite (+0.3)
    # Mots à ignorer pour le matching (trop génériques)
    ignore_words = {"fondation", "musée", "espace", "centre", "galerie", "museum"}
    favorite_fondations = profile.get("expo_fondations", [])
    if venue_lower and len(venue_lower) > 3:  # Éviter match sur venue vide
        for fav_fond in favorite_fondations:
            fav_lower = fav_fond.lower()
            if fav_lower in venue_lower or venue_lower in fav_lower:
                score += 0.3
                break
            # Vérifier les parties significatives du nom
            for part in fav_lower.split():
                if len(part) > 4 and part not in ignore_words and part in venue_lower:
                    score += 0.3
                    break
            if score >= 0.8:
                break

    return min(score, 1.0)


def _detect_expo_type(title: str, description: str, artists: List[str]) -> str:
    """Détecte le type d'exposition."""
    text = f"{title} {description}".lower()

    if "permanent" in text or "collection" in text:
        return "expo_permanente"
    if len(artists) > 2 or "collective" in text or "group" in text:
        return "expo_collective"
    if len(artists) == 1 or "solo" in text or "rétrospective" in text:
        return "expo_solo"

    return "autre"


# =============================================================================
# SCRAPERS PAR SOURCE
# =============================================================================

def _scrape_fondation_beyeler(verbose: bool = False) -> List[Dict]:
    """Scrape Fondation Beyeler (Riehen/Bâle)."""
    url = "https://www.fondationbeyeler.ch/fr/expositions"
    source = "Fondation Beyeler"
    city = "Riehen"
    exhibitions = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source}: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        # Site Angular/TYPO3 : extraire les expos depuis les liens
        # Les liens vers /fr/expositions/[nom-expo] contiennent les expos actuelles
        seen_titles = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)

            # Filtrer les liens vers des expositions spécifiques
            if "/fr/expositions/" in href and href != "/fr/expositions":
                # Exclure les pages génériques
                if "precedentes" in href.lower() or "archive" in href.lower():
                    continue

                # Extraire le nom de l'expo depuis l'URL ou le texte
                title = text if text and len(text) > 2 else ""
                if not title:
                    # Extraire depuis l'URL
                    parts = href.rstrip("/").split("/")
                    if parts:
                        title = parts[-1].replace("-", " ").title()

                if not _is_valid_title(title):
                    continue
                if title.lower() in seen_titles:
                    continue
                if title.lower() in ["lire plus", "en savoir plus", "expositions", "fr"]:
                    continue

                seen_titles.add(title.lower())

                expo_url = href if href.startswith("http") else f"https://www.fondationbeyeler.ch{href}"

                exhibitions.append({
                    "title": title,
                    "venue": source,
                    "city": city,
                    "distance_km": _get_distance(city),
                    "date_start": None,
                    "date_end": None,
                    "artists": [title] if title else [],  # L'artiste est souvent le titre
                    "description": "",
                    "type": "expo_solo",
                    "url": expo_url,
                    "profile_match": 0.0,
                    "source": source
                })

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {source}: ERREUR — {e}")

    return exhibitions


def _scrape_fondation_schneider(verbose: bool = False) -> List[Dict]:
    """Scrape Fondation François Schneider (Wattwiller)."""
    url = "https://www.fondationfrancoisschneider.org/expositions/"
    source = "Fondation François Schneider"
    city = "Wattwiller"
    exhibitions = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source}: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        # Chercher les blocs d'exposition (structure WordPress)
        for article in soup.select("article, .expo-item, .exhibition-card, [class*='expo'], .wp-block-group"):
            title_el = article.select_one("h2, h3, h4, .title")
            date_el = article.select_one(".date, .dates, [class*='date'], time, p")
            link_el = article.select_one("a[href*='exposition'], a[href*='expo']")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not _is_valid_title(title):
                continue

            dates_text = date_el.get_text(strip=True) if date_el else ""
            expo_url = link_el.get("href", "") if link_el else ""

            if expo_url and not expo_url.startswith("http"):
                expo_url = f"https://www.fondationfrancoisschneider.org{expo_url}"

            date_start, date_end = _extract_dates(dates_text)

            exhibitions.append({
                "title": title,
                "venue": source,
                "city": city,
                "distance_km": _get_distance(city),
                "date_start": date_start,
                "date_end": date_end,
                "artists": [],
                "description": "",
                "type": "autre",
                "url": expo_url or url,
                "profile_match": 0.0,
                "source": source
            })

        # Si aucun résultat, chercher dans les liens de la page
        if not exhibitions:
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if "/exposition" in href.lower() and text and len(text) > 5:
                    if _is_valid_title(text) and text not in ["Les expositions", "Expositions"]:
                        exhibitions.append({
                            "title": text,
                            "venue": source,
                            "city": city,
                            "distance_km": _get_distance(city),
                            "date_start": None,
                            "date_end": None,
                            "artists": [],
                            "description": "",
                            "type": "autre",
                            "url": href if href.startswith("http") else f"https://www.fondationfrancoisschneider.org{href}",
                            "profile_match": 0.0,
                            "source": source
                        })

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {source}: ERREUR — {e}")

    return exhibitions


def _scrape_fernet_branca(verbose: bool = False) -> List[Dict]:
    """Scrape Fondation Fernet-Branca (Saint-Louis)."""
    url = "https://www.fondationfernet-branca.org/expositions"
    source = "Fondation Fernet-Branca"
    city = "Saint-Louis"
    exhibitions = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source}: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        # Structure du site : h1 "Exposition en cours", h2 titre expo
        current_section = soup.find("h1", string=lambda t: t and "en cours" in t.lower())
        if current_section:
            # Chercher le h2 suivant (titre de l'expo)
            next_h2 = current_section.find_next("h2")
            if next_h2:
                title = next_h2.get_text(strip=True)

                # Chercher les dates dans le texte environnant
                parent = next_h2.find_parent(["section", "article", "div"])
                dates_text = ""
                description = ""
                if parent:
                    text = parent.get_text(" ", strip=True)
                    # Extraire dates
                    import re
                    date_match = re.search(r"(\d{1,2}\s+\w+\s+\d{4})\s*[-–à]\s*(\d{1,2}\s+\w+\s+\d{4})", text)
                    if date_match:
                        dates_text = f"{date_match.group(1)} - {date_match.group(2)}"
                    # Description (premiers 300 chars après le titre)
                    desc_el = parent.find("p")
                    if desc_el:
                        description = desc_el.get_text(strip=True)[:300]

                date_start, date_end = _extract_dates(dates_text)

                exhibitions.append({
                    "title": title,
                    "venue": source,
                    "city": city,
                    "distance_km": _get_distance(city),
                    "date_start": date_start,
                    "date_end": date_end,
                    "artists": [],
                    "description": description,
                    "type": "autre",
                    "url": url,
                    "profile_match": 0.0,
                    "source": source
                })

        # Fallback : chercher les h2 directement
        if not exhibitions:
            for h2 in soup.find_all("h2"):
                title = h2.get_text(strip=True)
                if title and _is_valid_title(title) and len(title) > 3:
                    # Ignorer les titres de section
                    if title.lower() in ["expositions passées", "expositions à venir", "exposition en cours"]:
                        continue
                    exhibitions.append({
                        "title": title,
                        "venue": source,
                        "city": city,
                        "distance_km": _get_distance(city),
                        "date_start": None,
                        "date_end": None,
                        "artists": [],
                        "description": "",
                        "type": "autre",
                        "url": url,
                        "profile_match": 0.0,
                        "source": source
                    })
                    break  # Prendre seulement la première

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {source}: ERREUR — {e}")

    return exhibitions


def _scrape_musee_wurth(verbose: bool = False) -> List[Dict]:
    """Scrape Musée Würth (Erstein)."""
    # La page /expositions ne liste pas les expos, on récupère depuis le menu
    url = "https://www.musee-wurth.fr/"
    source = "Musée Würth"
    city = "Erstein"
    exhibitions = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source}: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        # Chercher le lien vers l'expo en cours dans le menu
        # Structure: menu avec lien EXPOSITIONS qui pointe vers l'expo actuelle
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)

            # Le menu "EXPOSITIONS" pointe vers l'expo en cours
            if text.upper() == "EXPOSITIONS" and "musee-wurth.fr" in href:
                expo_url = href
                # Suivre le lien pour obtenir le titre
                try:
                    resp2 = requests.get(expo_url, headers=HEADERS, timeout=10)
                    soup2 = BeautifulSoup(resp2.content, "lxml")
                    title_el = soup2.find("h1")
                    title = title_el.get_text(strip=True) if title_el else ""

                    if title and _is_valid_title(title):
                        # Chercher les dates dans la page
                        text_content = soup2.get_text()
                        import re
                        date_match = re.search(
                            r"(\d{1,2}\s+\w+\s+\d{4})\s*[-–àau]+\s*(\d{1,2}\s+\w+\s+\d{4})",
                            text_content
                        )
                        dates_text = f"{date_match.group(1)} - {date_match.group(2)}" if date_match else ""
                        date_start, date_end = _extract_dates(dates_text)

                        exhibitions.append({
                            "title": title,
                            "venue": source,
                            "city": city,
                            "distance_km": _get_distance(city),
                            "date_start": date_start,
                            "date_end": date_end,
                            "artists": [],
                            "description": "",
                            "type": "expo_collective",
                            "url": expo_url,
                            "profile_match": 0.0,
                            "source": source
                        })
                except Exception:
                    pass
                break

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {source}: ERREUR — {e}")

    return exhibitions


def _scrape_musees_strasbourg(verbose: bool = False) -> List[Dict]:
    """Scrape Musées de Strasbourg."""
    url = "https://www.musees.strasbourg.eu/expositions"
    source = "Musées de Strasbourg"
    city = "Strasbourg"
    exhibitions = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source}: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        for item in soup.select("article, .expo, .exhibition-card, [class*='expo']"):
            title_el = item.select_one("h2, h3, .title")
            museum_el = item.select_one(".museum, .lieu, [class*='museum'], [class*='lieu']")
            date_el = item.select_one(".date, [class*='date']")
            link_el = item.select_one("a[href]")
            desc_el = item.select_one("p, .description")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            museum = museum_el.get_text(strip=True) if museum_el else source
            dates_text = date_el.get_text(strip=True) if date_el else ""
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""
            expo_url = link_el.get("href", "") if link_el else ""

            if expo_url and not expo_url.startswith("http"):
                expo_url = f"https://www.musees.strasbourg.eu{expo_url}"

            date_start, date_end = _extract_dates(dates_text)

            exhibitions.append({
                "title": title,
                "venue": museum,
                "city": city,
                "distance_km": _get_distance(city),
                "date_start": date_start,
                "date_end": date_end,
                "artists": [],
                "description": description,
                "type": "autre",
                "url": expo_url or url,
                "profile_match": 0.0,
                "source": source
            })

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {source}: ERREUR — {e}")

    return exhibitions


def _scrape_kunstmuseum_basel(verbose: bool = False) -> List[Dict]:
    """Scrape Kunstmuseum Basel."""
    url = "https://www.kunstmuseumbasel.ch/fr/expositions"
    source = "Kunstmuseum Basel"
    city = "Bâle"
    exhibitions = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source}: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        # Structure du site : les h2 contiennent les titres d'expo
        # Ignorer les h2 de section ("Expositions spéciales", "Expositions", etc.)
        section_titles = ["expositions spéciales", "expositions", "espaces focaux", "projets"]

        for h2 in soup.find_all("h2"):
            title = h2.get_text(strip=True)

            if not _is_valid_title(title):
                continue
            if title.lower() in section_titles:
                continue
            if "&" in title and len(title) < 5:  # "de &" type links
                continue

            # Chercher un lien parent ou enfant
            link_el = h2.find_parent("a") or h2.find("a") or h2.find_next("a")
            expo_url = ""
            if link_el and link_el.get("href"):
                href = link_el.get("href")
                if "exposition" in href or "ausstellung" in href:
                    expo_url = href if href.startswith("http") else f"https://www.kunstmuseumbasel.ch{href}"

            exhibitions.append({
                "title": title,
                "venue": source,
                "city": city,
                "distance_km": _get_distance(city),
                "date_start": None,
                "date_end": None,
                "artists": [title],  # Le titre est souvent l'artiste
                "description": "",
                "type": "expo_solo",
                "url": expo_url or url,
                "profile_match": 0.0,
                "source": source
            })

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {source}: ERREUR — {e}")

    return exhibitions


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def _is_valid_title(title: str) -> bool:
    """Vérifie si le titre est valide (pas de template, pas vide)."""
    if not title or len(title) < 3:
        return False
    # Exclure les variables de template
    if "{{" in title or "}}" in title:
        return False
    # Exclure les titres génériques
    title_lower = title.lower().strip()
    generic = [
        "en savoir plus", "lire la suite", "voir plus", "expositions",
        "expositions en cours", "expositions passées", "expositions à venir",
        "exposition en cours", "découvrez toutes nos expositions",
        "découvrez toutes nos expositions passées", "les expositions"
    ]
    for g in generic:
        if title_lower == g or title_lower.startswith(g):
            return False
    return True


def get_exhibitions(period: Dict, profile: Dict, verbose: bool = False) -> List[Dict]:
    """
    Récupère toutes les expositions pour une période.

    Args:
        period: Dict avec start, end
        profile: Dict du profil utilisateur
        verbose: Si True, affiche les détails de scraping

    Returns:
        Liste d'expositions triée par profile_match
    """
    start_date = period.get("start")
    end_date = period.get("end")

    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    # Clé de cache
    cache_key = f"exhibitions_{start_date}_{end_date}"

    # Vérifier le cache
    cached = cache_get(cache_key)
    if cached:
        print("  Expositions : CACHE HIT")
        # Recalculer profile_match avec le profil actuel
        for expo in cached:
            expo["profile_match"] = _calculate_profile_match(
                expo["title"],
                expo["artists"],
                expo["description"],
                expo["venue"],
                profile
            )
        cached.sort(key=lambda x: (-x["profile_match"], x["distance_km"]))
        return cached

    print("  Expositions : CACHE MISS → scraping")

    all_exhibitions = []
    stats = {}

    # Scraper toutes les sources
    scrapers = [
        ("Fondation Beyeler", _scrape_fondation_beyeler),
        ("Fondation Schneider", _scrape_fondation_schneider),
        ("Espace Fernet-Branca", _scrape_fernet_branca),
        ("Musée Würth", _scrape_musee_wurth),
        ("Musées de Strasbourg", _scrape_musees_strasbourg),
        ("Kunstmuseum Basel", _scrape_kunstmuseum_basel),
    ]

    for source_name, scraper_fn in scrapers:
        try:
            expos = scraper_fn(verbose=verbose)
            all_exhibitions.extend(expos)
            stats[source_name] = len(expos)
        except Exception as e:
            stats[source_name] = f"ERREUR: {e}"
            if verbose:
                print(f"  {source_name}: Exception — {e}")

    if verbose:
        print()
        print("Résumé sources:")
        for src, count in stats.items():
            print(f"  {src}: {count}")

    # Filtrer les titres invalides
    all_exhibitions = [e for e in all_exhibitions if _is_valid_title(e.get("title", ""))]

    # Filtrer par période
    filtered = []
    cutoff_future = end_date + timedelta(days=30)

    for expo in all_exhibitions:
        expo_start = expo.get("date_start")
        expo_end = expo.get("date_end")

        # Si pas de dates, inclure par défaut
        if not expo_start and not expo_end:
            filtered.append(expo)
            continue

        # Expo active pendant la période
        if expo_end and expo_end >= start_date:
            if not expo_start or expo_start <= end_date:
                filtered.append(expo)
                continue

        # Expo qui démarre dans les 30 jours
        if expo_start and expo_start <= cutoff_future:
            if not expo_end or expo_end >= start_date:
                filtered.append(expo)
                continue

    # Déduplication : filtrer les expositions déjà vues (1 an)
    from engine.profile import get_seen_items_normalized, normalize_for_matching

    seen_expos = get_seen_items_normalized('expos', days=365)

    deduplicated = []
    for expo in filtered:
        expo_normalized = normalize_for_matching(expo["title"])
        expo_venue_key = f"{expo_normalized} {normalize_for_matching(expo['venue'])}"

        if expo_normalized not in seen_expos and expo_venue_key not in seen_expos:
            deduplicated.append(expo)
        elif verbose:
            print(f"  [SKIP] Expo déjà vue : {expo['title']} @ {expo['venue']}")

    filtered = deduplicated

    # Calculer profile_match
    for expo in filtered:
        expo["profile_match"] = _calculate_profile_match(
            expo["title"],
            expo["artists"],
            expo["description"],
            expo["venue"],
            profile
        )
        # Détecter le type si pas déjà fait
        if expo["type"] == "autre":
            expo["type"] = _detect_expo_type(
                expo["title"],
                expo["description"],
                expo["artists"]
            )

    # Exclure expos permanentes sauf si profile_match > 0.4
    filtered = [
        e for e in filtered
        if e["type"] != "expo_permanente" or e["profile_match"] > 0.4
    ]

    # Trier par profile_match décroissant, puis distance
    filtered.sort(key=lambda x: (-x["profile_match"], x["distance_km"]))

    # Mettre en cache
    cache_set(cache_key, filtered, CACHE_TTL.get("exhibitions", 720))

    return filtered


def format_exhibitions_context(exhibitions: List[Dict]) -> str:
    """Formate les expositions pour le contexte Claude."""
    if not exhibitions:
        return "Expositions : aucune exposition trouvée pour cette période."

    top_expos = exhibitions[:4]
    lines = ["Expositions en cours :"]

    for expo in top_expos:
        # Gérer date_start qui peut être date, str (depuis cache JSON) ou None
        date_start = expo["date_start"]
        if date_start:
            if isinstance(date_start, str):
                try:
                    from datetime import datetime, date
                    date_obj = datetime.strptime(date_start, "%Y-%m-%d").date()
                    date_start_str = date_obj.strftime("%d/%m")
                except ValueError:
                    date_start_str = "?"
            elif isinstance(date_start, date):
                date_start_str = date_start.strftime("%d/%m")
            else:
                date_start_str = "?"
        else:
            date_start_str = "?"

        # Gérer date_end de la même manière
        date_end = expo["date_end"]
        if date_end:
            if isinstance(date_end, str):
                try:
                    from datetime import datetime, date
                    date_obj = datetime.strptime(date_end, "%Y-%m-%d").date()
                    date_end_str = date_obj.strftime("%d/%m/%Y")
                except ValueError:
                    date_end_str = "?"
            elif isinstance(date_end, date):
                date_end_str = date_end.strftime("%d/%m/%Y")
            else:
                date_end_str = "?"
        else:
            date_end_str = "?"

        lines.append(f"- {expo['title']} — {expo['venue']} ({expo['city']}, {expo['distance_km']:.0f}km)")
        lines.append(f"  Du {date_start_str} au {date_end_str}")
        lines.append(f"  Match profil : {expo['profile_match']:.1f}")

        if expo["artists"]:
            lines.append(f"  Artistes : {', '.join(expo['artists'][:3])}")

    return "\n".join(lines)


def display_exhibitions(exhibitions: List[Dict]) -> None:
    """Affiche les expositions dans le terminal (pour debug)."""
    print(f"\n{'='*50}")
    print("EXPOSITIONS")
    print(f"{'='*50}")

    if not exhibitions:
        print("Aucune exposition trouvée")
        return

    # Stats par source
    sources = {}
    for e in exhibitions:
        src = e.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1

    print(f"\nSources : {sources}")
    print(f"Total : {len(exhibitions)} expositions")

    # Top 3 par profile_match
    print(f"\n{'—'*50}")
    print("TOP 3 par correspondance profil")
    print(f"{'—'*50}")

    for i, expo in enumerate(exhibitions[:3], 1):
        # Gérer date_start qui peut être date, str (depuis cache JSON) ou None
        date_start = expo["date_start"]
        if date_start:
            if isinstance(date_start, str):
                try:
                    from datetime import datetime, date
                    date_obj = datetime.strptime(date_start, "%Y-%m-%d").date()
                    date_start_str = date_obj.strftime("%d/%m/%Y")
                except ValueError:
                    date_start_str = "NC"
            elif isinstance(date_start, date):
                date_start_str = date_start.strftime("%d/%m/%Y")
            else:
                date_start_str = "NC"
        else:
            date_start_str = "NC"

        # Gérer date_end de la même manière
        date_end = expo["date_end"]
        if date_end:
            if isinstance(date_end, str):
                try:
                    from datetime import datetime, date
                    date_obj = datetime.strptime(date_end, "%Y-%m-%d").date()
                    date_end_str = date_obj.strftime("%d/%m/%Y")
                except ValueError:
                    date_end_str = "NC"
            elif isinstance(date_end, date):
                date_end_str = date_end.strftime("%d/%m/%Y")
            else:
                date_end_str = "NC"
        else:
            date_end_str = "NC"

        print(f"\n{i}. {expo['title']}")
        print(f"   Lieu : {expo['venue']} ({expo['city']})")
        print(f"   Dates : {date_start_str} — {date_end_str}")
        print(f"   Distance : {expo['distance_km']:.0f} km")
        print(f"   Match profil : {expo['profile_match']:.2f}")
        if expo["artists"]:
            print(f"   Artistes : {', '.join(expo['artists'])}")

    print(f"\n{'='*50}\n")
