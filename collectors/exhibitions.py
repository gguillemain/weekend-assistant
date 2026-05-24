"""
Module de collecte des expositions via scraping des fondations et musées locaux.
"""

import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import re

import config

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

        # Chercher les blocs d'exposition
        # Structure typique: articles ou divs avec titres et dates
        for article in soup.select("article, .exhibition-item, .expo-card, [class*='exhibition']"):
            title_el = article.select_one("h2, h3, .title, [class*='title']")
            date_el = article.select_one(".date, .dates, [class*='date'], time")
            desc_el = article.select_one("p, .description, .excerpt, [class*='desc']")
            link_el = article.select_one("a[href*='exposition'], a[href*='exhibition']")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            dates_text = date_el.get_text(strip=True) if date_el else ""
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""
            expo_url = link_el.get("href", "") if link_el else ""

            if expo_url and not expo_url.startswith("http"):
                expo_url = f"https://www.fondationbeyeler.ch{expo_url}"

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
                "url": expo_url or url,
                "profile_match": 0.0,
                "source": source
            })

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {source}: ERREUR — {e}")

    return exhibitions


def _scrape_fondation_schneider(verbose: bool = False) -> List[Dict]:
    """Scrape Fondation Schneider (Wattwiller)."""
    url = "https://www.fondationschneider.fr/expositions"
    source = "Fondation Schneider"
    city = "Wattwiller"
    exhibitions = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source}: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        for article in soup.select("article, .expo, .exhibition, [class*='expo']"):
            title_el = article.select_one("h2, h3, .title")
            date_el = article.select_one(".date, .dates, [class*='date']")
            artist_el = article.select_one(".artist, .artiste, [class*='artist']")
            link_el = article.select_one("a[href]")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            dates_text = date_el.get_text(strip=True) if date_el else ""
            artist_text = artist_el.get_text(strip=True) if artist_el else ""
            expo_url = link_el.get("href", "") if link_el else ""

            if expo_url and not expo_url.startswith("http"):
                expo_url = f"https://www.fondationschneider.fr{expo_url}"

            date_start, date_end = _extract_dates(dates_text)
            artists = [a.strip() for a in artist_text.split(",") if a.strip()] if artist_text else []

            exhibitions.append({
                "title": title,
                "venue": source,
                "city": city,
                "distance_km": _get_distance(city),
                "date_start": date_start,
                "date_end": date_end,
                "artists": artists,
                "description": "",
                "type": _detect_expo_type(title, "", artists),
                "url": expo_url or url,
                "profile_match": 0.0,
                "source": source
            })

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {source}: ERREUR — {e}")

    return exhibitions


def _scrape_fernet_branca(verbose: bool = False) -> List[Dict]:
    """Scrape Espace Fernet-Branca (Saint-Louis)."""
    url = "https://www.fernet-branca.com/agenda"
    source = "Espace Fernet-Branca"
    city = "Saint-Louis"
    exhibitions = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source}: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        for item in soup.select("article, .event, .agenda-item, [class*='event']"):
            title_el = item.select_one("h2, h3, .title")
            date_el = item.select_one(".date, [class*='date']")
            type_el = item.select_one(".type, .category, [class*='type']")
            link_el = item.select_one("a[href]")
            desc_el = item.select_one("p, .description")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            dates_text = date_el.get_text(strip=True) if date_el else ""
            event_type = type_el.get_text(strip=True).lower() if type_el else ""
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""
            expo_url = link_el.get("href", "") if link_el else ""

            # Filtrer : garder expos, ignorer concerts
            if "concert" in event_type or "musique" in event_type:
                continue

            if expo_url and not expo_url.startswith("http"):
                expo_url = f"https://www.fernet-branca.com{expo_url}"

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
                "url": expo_url or url,
                "profile_match": 0.0,
                "source": source
            })

    except requests.exceptions.RequestException as e:
        if verbose:
            print(f"  {source}: ERREUR — {e}")

    return exhibitions


def _scrape_musee_wurth(verbose: bool = False) -> List[Dict]:
    """Scrape Musée Würth (Erstein)."""
    url = "https://www.musee-wurth.fr/expositions"
    source = "Musée Würth"
    city = "Erstein"
    exhibitions = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if verbose:
            print(f"  {source}: HTTP {resp.status_code}")
        resp.raise_for_status()

        soup = BeautifulSoup(resp.content, "lxml")

        for item in soup.select("article, .expo, [class*='exhibition'], [class*='expo']"):
            title_el = item.select_one("h2, h3, .title")
            date_el = item.select_one(".date, [class*='date']")
            artist_el = item.select_one(".artist, [class*='artist']")
            link_el = item.select_one("a[href]")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            dates_text = date_el.get_text(strip=True) if date_el else ""
            artist_text = artist_el.get_text(strip=True) if artist_el else ""
            expo_url = link_el.get("href", "") if link_el else ""

            if expo_url and not expo_url.startswith("http"):
                expo_url = f"https://www.musee-wurth.fr{expo_url}"

            date_start, date_end = _extract_dates(dates_text)
            artists = [a.strip() for a in artist_text.split(",") if a.strip()] if artist_text else []

            exhibitions.append({
                "title": title,
                "venue": source,
                "city": city,
                "distance_km": _get_distance(city),
                "date_start": date_start,
                "date_end": date_end,
                "artists": artists,
                "description": "",
                "type": _detect_expo_type(title, "", artists),
                "url": expo_url or url,
                "profile_match": 0.0,
                "source": source
            })

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

        for item in soup.select("article, .exhibition, [class*='exhibition'], [class*='expo']"):
            title_el = item.select_one("h2, h3, .title")
            date_el = item.select_one(".date, [class*='date']")
            desc_el = item.select_one("p, .description, .lead")
            link_el = item.select_one("a[href]")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            dates_text = date_el.get_text(strip=True) if date_el else ""
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""
            expo_url = link_el.get("href", "") if link_el else ""

            if expo_url and not expo_url.startswith("http"):
                expo_url = f"https://www.kunstmuseumbasel.ch{expo_url}"

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
    generic = ["en savoir plus", "lire la suite", "voir plus", "expositions"]
    if title.lower().strip() in generic:
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

    return filtered


def format_exhibitions_context(exhibitions: List[Dict]) -> str:
    """Formate les expositions pour le contexte Claude."""
    if not exhibitions:
        return "Expositions : aucune exposition trouvée pour cette période."

    top_expos = exhibitions[:4]
    lines = ["Expositions en cours :"]

    for expo in top_expos:
        date_start_str = expo["date_start"].strftime("%d/%m") if expo["date_start"] else "?"
        date_end_str = expo["date_end"].strftime("%d/%m/%Y") if expo["date_end"] else "?"

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
        date_start_str = expo["date_start"].strftime("%d/%m/%Y") if expo["date_start"] else "NC"
        date_end_str = expo["date_end"].strftime("%d/%m/%Y") if expo["date_end"] else "NC"

        print(f"\n{i}. {expo['title']}")
        print(f"   Lieu : {expo['venue']} ({expo['city']})")
        print(f"   Dates : {date_start_str} — {date_end_str}")
        print(f"   Distance : {expo['distance_km']:.0f} km")
        print(f"   Match profil : {expo['profile_match']:.2f}")
        if expo["artists"]:
            print(f"   Artistes : {', '.join(expo['artists'])}")

    print(f"\n{'='*50}\n")
