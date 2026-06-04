"""
Module de suggestions de city-breaks européens.
Liste statique avec scoring par saison et préférences utilisateur.
"""

from datetime import date, datetime
from typing import Dict, List, Optional


# =============================================================================
# LISTE DES CITY-BREAKS
# =============================================================================

CITY_BREAKS = [
    {
        "destination": "Londres",
        "country": "Royaume-Uni",
        "iata": "LGW",
        "transport": "avion",
        "seasons": ["all"],
        "duration_days": [4, 5],
        "budget": "€€€",
        "geraldine_loves": True,
        "tags": ["culture", "musique", "new wave", "musées", "théâtre", "The Cure", "Pulp"],
        "notes": "The Cure, Pulp — Londres est leur ville. Concerts, V&A, Tate Modern.",
        "highlights": ["Tate Modern", "V&A Museum", "Camden", "concerts", "West End"],
    },
    {
        "destination": "Budapest",
        "country": "Hongrie",
        "iata": "BUD",
        "transport": "avion",
        "seasons": ["automne", "hiver", "printemps"],
        "duration_days": [5, 6],
        "budget": "€",
        "geraldine_loves": False,
        "tags": ["culture", "thermaux", "gastronomie", "architecture", "Art Nouveau"],
        "highlights": ["Bains Széchenyi", "Parlement", "Quartier juif", "ruinbars"],
    },
    {
        "destination": "Prague",
        "country": "Tchéquie",
        "iata": "PRG",
        "transport": "avion",
        "seasons": ["automne", "hiver", "printemps"],
        "duration_days": [4, 5],
        "budget": "€",
        "geraldine_loves": False,
        "tags": ["culture", "architecture", "bière", "histoire", "gothique"],
        "highlights": ["Château de Prague", "Pont Charles", "Mala Strana", "brasseries"],
    },
    {
        "destination": "Vienne",
        "country": "Autriche",
        "iata": "VIE",
        "transport": ["avion", "train"],
        "seasons": ["automne", "hiver", "printemps"],
        "duration_days": [4, 5],
        "budget": "€€",
        "geraldine_loves": False,
        "tags": ["musées", "opéra", "gastronomie", "Klimt", "surréalisme", "Schiele", "art"],
        "highlights": ["Musée Leopold", "Belvedere", "Naschmarkt", "cafés viennois"],
    },
    {
        "destination": "Amsterdam",
        "country": "Pays-Bas",
        "iata": "AMS",
        "transport": "avion",
        "seasons": ["printemps", "automne"],
        "duration_days": [3, 4],
        "budget": "€€",
        "geraldine_loves": False,
        "tags": ["musées", "vélo", "canaux", "Rijksmuseum", "Van Gogh", "art"],
        "highlights": ["Rijksmuseum", "Van Gogh Museum", "Anne Frank", "Jordaan"],
    },
    {
        "destination": "Édimbourg",
        "country": "Écosse",
        "iata": "EDI",
        "transport": "avion",
        "seasons": ["été", "printemps"],
        "duration_days": [4, 5],
        "budget": "€€",
        "geraldine_loves": False,
        "tags": ["highlands", "whisky", "festival", "châteaux", "nature", "littérature"],
        "highlights": ["Royal Mile", "Arthur's Seat", "Whisky trail", "Fringe Festival"],
    },
    {
        "destination": "Lisbonne",
        "country": "Portugal",
        "iata": "LIS",
        "transport": "avion",
        "seasons": ["printemps", "automne"],
        "duration_days": [5, 6],
        "budget": "€",
        "geraldine_loves": False,
        "tags": ["culture", "fado", "gastronomie", "azulejos", "street art"],
        "highlights": ["Alfama", "Belém", "LX Factory", "pastéis de nata"],
    },
    {
        "destination": "Dublin",
        "country": "Irlande",
        "iata": "DUB",
        "transport": "avion",
        "seasons": ["été", "printemps"],
        "duration_days": [4, 5],
        "budget": "€€",
        "geraldine_loves": False,
        "tags": ["musique", "pubs", "littérature", "Fontaines D.C.", "post-punk", "concerts"],
        "notes": "Fontaines D.C. viennent de Dublin — la scène post-punk irlandaise est vivante.",
        "highlights": ["Temple Bar", "Trinity College", "Guinness", "concerts live"],
    },
    {
        "destination": "Copenhague",
        "country": "Danemark",
        "iata": "CPH",
        "transport": "avion",
        "seasons": ["été", "printemps"],
        "duration_days": [4, 5],
        "budget": "€€€",
        "geraldine_loves": False,
        "tags": ["design", "gastronomie", "vélo", "hygge", "architecture moderne"],
        "highlights": ["Nyhavn", "Louisiana Museum", "Tivoli", "nouvelle cuisine nordique"],
    },
    {
        "destination": "Séville",
        "country": "Espagne",
        "iata": "SVQ",
        "transport": "avion",
        "seasons": ["printemps", "automne"],
        "duration_days": [5, 6],
        "budget": "€",
        "geraldine_loves": False,
        "tags": ["flamenco", "architecture", "gastronomie", "soleil", "Alcazar"],
        "highlights": ["Alcazar", "Cathédrale", "tapas", "spectacle flamenco"],
    },
    {
        "destination": "Porto",
        "country": "Portugal",
        "iata": "OPO",
        "transport": "avion",
        "seasons": ["printemps", "automne"],
        "duration_days": [4, 5],
        "budget": "€",
        "geraldine_loves": False,
        "tags": ["vin", "azulejos", "gastronomie", "Douro", "architecture"],
        "highlights": ["Ribeira", "caves de Porto", "Livraria Lello", "croisière Douro"],
    },
    {
        "destination": "Cracovie",
        "country": "Pologne",
        "iata": "KRK",
        "transport": "avion",
        "seasons": ["automne", "hiver", "printemps"],
        "duration_days": [4, 5],
        "budget": "€",
        "geraldine_loves": False,
        "tags": ["histoire", "culture", "gastronomie", "patrimoine"],
        "highlights": ["Vieille ville", "Kazimierz", "Wieliczka", "Auschwitz"],
    },
    {
        "destination": "Rome",
        "country": "Italie",
        "iata": "FCO",
        "transport": "avion",
        "seasons": ["printemps", "automne"],
        "duration_days": [4, 5],
        "budget": "€€",
        "geraldine_loves": False,
        "tags": ["histoire", "art", "gastronomie", "antiquité", "Vatican"],
        "highlights": ["Vatican", "Colisée", "Trastevere", "Galleria Borghese"],
    },
    {
        "destination": "Barcelone",
        "country": "Espagne",
        "iata": "BCN",
        "transport": "avion",
        "seasons": ["printemps", "automne"],
        "duration_days": [4, 5],
        "budget": "€€",
        "geraldine_loves": False,
        "tags": ["Gaudí", "architecture", "plage", "gastronomie", "art"],
        "highlights": ["Sagrada Familia", "Park Güell", "Barrio Gótico", "Fundació Miró"],
    },
]


# =============================================================================
# UTILITAIRES
# =============================================================================

def _get_current_season(dt: date) -> str:
    """Détermine la saison pour une date donnée."""
    month = dt.month
    if month in [3, 4, 5]:
        return "printemps"
    elif month in [6, 7, 8]:
        return "été"
    elif month in [9, 10, 11]:
        return "automne"
    else:
        return "hiver"


def _calculate_season_score(city: Dict, season: str) -> float:
    """Calcule le score saison (0-0.4)."""
    seasons = city.get("seasons", [])

    if "all" in seasons:
        return 0.3
    elif season in seasons:
        return 0.4
    else:
        return 0.1  # Hors saison


def _calculate_preference_score(city: Dict, profile: Dict) -> float:
    """
    Calcule le score préférences utilisateur (0-0.5).

    Args:
        city: Dict du city-break
        profile: Dict avec music_artists, expo_artists, etc.
    """
    score = 0.0
    tags = [t.lower() for t in city.get("tags", [])]

    # Tags musicaux (artistes favoris)
    music_artists = profile.get("music_artists", [])
    for artist in music_artists:
        if artist.lower() in tags or artist.lower() in " ".join(tags):
            score += 0.3
            break

    # Tags expos (artistes expo)
    expo_artists = profile.get("expo_artists", [])
    for artist in expo_artists:
        if artist.lower() in tags:
            score += 0.2
            break

    # Géraldine loves
    if city.get("geraldine_loves", False):
        score += 0.2

    return min(score, 0.5)


def _calculate_novelty_score(city: Dict, seen_destinations: List[str]) -> float:
    """
    Calcule le score nouveauté (0-0.15 avec pénalité si déjà visité).

    Args:
        city: Dict du city-break
        seen_destinations: Liste des destinations récentes
    """
    destination = city.get("destination", "").lower()

    # Pénalité si déjà visité récemment
    for seen in seen_destinations:
        if destination in seen.lower() or seen.lower() in destination:
            return -0.3

    return 0.15  # Bonus nouveauté


def _get_budget_estimate(city: Dict) -> str:
    """Estime le budget total pour un city-break."""
    budget_symbol = city.get("budget", "€€")
    duration = city.get("duration_days", [4, 5])
    avg_duration = sum(duration) / len(duration)

    # Estimations par budget
    estimates = {
        "€": {"flight": 100, "hotel_night": 60, "daily": 50},
        "€€": {"flight": 150, "hotel_night": 90, "daily": 70},
        "€€€": {"flight": 200, "hotel_night": 130, "daily": 100},
    }

    est = estimates.get(budget_symbol, estimates["€€"])
    nights = avg_duration - 1
    total = est["flight"] + (est["hotel_night"] * nights) + (est["daily"] * avg_duration)

    return f"{total:.0f}€"


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def get_citybreaks(
    vacation_period: Dict,
    flights: List[Dict],
    profile: Dict
) -> List[Dict]:
    """
    Récupère les city-breaks recommandés avec scoring.

    Args:
        vacation_period: Dict avec start, end, days, label
        flights: Liste des vols pas chers trouvés
        profile: Dict avec music_artists, expo_artists, etc.

    Returns:
        Liste de city-breaks triés par travel_score
    """
    start_date = vacation_period.get("start")
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

    season = _get_current_season(start_date)

    # Destinations déjà visitées (depuis activity_log)
    seen_destinations = profile.get("trips_seen_recent", [])

    # Index des vols par destination
    flights_by_dest = {}
    for flight in flights:
        dest = flight.get("destination", "").lower()
        if dest not in flights_by_dest or flight["budget_score"] > flights_by_dest[dest]["budget_score"]:
            flights_by_dest[dest] = flight

    results = []

    for city in CITY_BREAKS:
        dest_lower = city["destination"].lower()

        # Score saison
        season_score = _calculate_season_score(city, season)

        # Score préférences
        preference_score = _calculate_preference_score(city, profile)

        # Score nouveauté
        novelty_score = _calculate_novelty_score(city, seen_destinations)

        # Score budget (depuis vols ou estimé)
        if dest_lower in flights_by_dest:
            flight = flights_by_dest[dest_lower]
            budget_score = flight["budget_score"]
            flight_info = {
                "price": flight["price_flight"],
                "airline": flight["airline"],
                "total_estimate": flight["price_total_estimate"],
            }
        else:
            # Pas de vol trouvé, estimer
            budget_score = 0.5
            flight_info = None

        # Score total
        travel_score = (
            budget_score * 0.35 +
            season_score * 0.25 +
            preference_score * 0.25 +
            novelty_score * 0.15
        )

        results.append({
            **city,
            "season": season,
            "season_score": round(season_score, 2),
            "preference_score": round(preference_score, 2),
            "novelty_score": round(novelty_score, 2),
            "budget_score": round(budget_score, 2),
            "travel_score": round(travel_score, 2),
            "flight_info": flight_info,
            "budget_estimate": _get_budget_estimate(city),
        })

    # Trier par travel_score décroissant
    results.sort(key=lambda c: c["travel_score"], reverse=True)

    print(f"  City-breaks : {len(results)} destinations scorées")

    return results


def format_citybreaks_context(citybreaks: List[Dict], limit: int = 3) -> str:
    """Formate les city-breaks pour le contexte Claude."""
    if not citybreaks:
        return "Aucun city-break recommandé."

    lines = [f"City-breaks recommandés ({len(citybreaks)} destinations) :"]

    for city in citybreaks[:limit]:
        flight_str = ""
        if city.get("flight_info"):
            fi = city["flight_info"]
            flight_str = f" | Vol {fi['airline']} : {fi['price']:.0f}€ A/R"

        tags_str = ", ".join(city.get("tags", [])[:4])

        lines.append(
            f"- {city['destination']} ({city['country']}) : "
            f"score {city['travel_score']:.2f}{flight_str}"
        )
        lines.append(f"  Tags : {tags_str}")
        if city.get("notes"):
            lines.append(f"  Note : {city['notes']}")

    return "\n".join(lines)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST COLLECTOR TRAVEL_CITYBREAKS")
    print("=" * 60)

    # Profil test
    test_profile = {
        "music_artists": ["The Cure", "Pulp", "Fontaines D.C.", "Bertrand Belin"],
        "expo_artists": ["Soulages", "Banksy", "Klimt"],
        "trips_seen_recent": [],
    }

    # Vols test
    test_flights = [
        {
            "destination": "Dublin",
            "price_flight": 89,
            "airline": "Ryanair",
            "budget_score": 0.9,
            "price_total_estimate": 450,
        },
        {
            "destination": "Londres",
            "price_flight": 120,
            "airline": "EasyJet",
            "budget_score": 0.7,
            "price_total_estimate": 680,
        },
    ]

    # Période test (printemps)
    test_period = {
        "start": "2026-04-15",
        "end": "2026-04-22",
        "days": 7,
        "label": "Vacances de printemps",
    }

    citybreaks = get_citybreaks(test_period, test_flights, test_profile)

    print(f"\nSaison détectée : {citybreaks[0]['season'] if citybreaks else 'N/A'}")
    print(f"\nTop 5 city-breaks par travel_score :")

    for i, city in enumerate(citybreaks[:5], 1):
        print(f"\n  {i}. {city['destination']} ({city['country']})")
        print(f"     Score total : {city['travel_score']:.2f}")
        print(f"     - Saison : {city['season_score']:.2f}")
        print(f"     - Préférences : {city['preference_score']:.2f}")
        print(f"     - Budget : {city['budget_score']:.2f}")
        print(f"     - Nouveauté : {city['novelty_score']:.2f}")
        if city.get("geraldine_loves"):
            print(f"     ❤️ Géraldine loves!")
        if city.get("notes"):
            print(f"     📝 {city['notes']}")
