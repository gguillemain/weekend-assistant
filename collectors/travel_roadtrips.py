"""
Module de suggestions de roadtrips en voiture depuis Guebwiller.
Destinations < 8h de route avec scoring par saison et préférences.
"""

from datetime import date, datetime
from typing import Dict, List


# =============================================================================
# LISTE DES ROADTRIPS
# =============================================================================

ROAD_TRIPS = [
    {
        "destination": "Forêt Noire",
        "country": "Allemagne",
        "drive_hours": 1.5,
        "drive_km": 90,
        "seasons": ["hiver", "automne"],
        "duration_days": [2, 3],
        "budget": "€",
        "highlights": ["Baden-Baden", "Freiburg", "Triberg", "Titisee"],
        "tags": ["nature", "spa", "gastronomie", "forêt", "cascades"],
        "notes": "Idéal pour un week-end prolongé. Marchés de Noël en décembre.",
    },
    {
        "destination": "Lac de Garde",
        "country": "Italie",
        "drive_hours": 4.5,
        "drive_km": 420,
        "seasons": ["printemps", "été"],
        "duration_days": [4, 5],
        "budget": "€€",
        "highlights": ["Sirmione", "Malcesine", "Riva del Garda", "Limone"],
        "tags": ["lac", "nature", "gastronomie", "dolce vita", "vélo"],
    },
    {
        "destination": "Lac Majeur",
        "country": "Italie/Suisse",
        "drive_hours": 3.5,
        "drive_km": 320,
        "seasons": ["printemps", "été"],
        "duration_days": [3, 4],
        "budget": "€€",
        "highlights": ["Stresa", "Îles Borromées", "Locarno", "Ascona"],
        "tags": ["lac", "jardins", "nature", "belle époque"],
    },
    {
        "destination": "Lac de Côme",
        "country": "Italie",
        "drive_hours": 3.0,
        "drive_km": 280,
        "seasons": ["printemps", "été"],
        "duration_days": [3, 4],
        "budget": "€€€",
        "highlights": ["Bellagio", "Varenna", "Villa Carlotta", "Como"],
        "tags": ["lac", "élégance", "nature", "villas", "jardins"],
        "notes": "Le plus chic des lacs italiens. Réserver à l'avance.",
    },
    {
        "destination": "Tyrol autrichien",
        "country": "Autriche",
        "drive_hours": 3.5,
        "drive_km": 320,
        "seasons": ["hiver", "été"],
        "duration_days": [4, 5],
        "budget": "€€",
        "highlights": ["Innsbruck", "Hall in Tirol", "Seefeld", "Stubaital"],
        "tags": ["montagne", "culture", "gastronomie", "ski", "randonnée"],
    },
    {
        "destination": "Salzbourg",
        "country": "Autriche",
        "drive_hours": 4.0,
        "drive_km": 380,
        "seasons": ["all"],
        "duration_days": [3, 4],
        "budget": "€€",
        "highlights": ["Centre historique", "Forteresse", "Hellbrunn", "Hallstatt"],
        "tags": ["musique classique", "culture", "patrimoine UNESCO", "Mozart"],
        "notes": "Hallstatt à 1h, incontournable. Festival en été.",
    },
    {
        "destination": "Dolomites",
        "country": "Italie",
        "drive_hours": 4.5,
        "drive_km": 420,
        "seasons": ["été", "automne"],
        "duration_days": [4, 5],
        "budget": "€€",
        "highlights": ["Cortina d'Ampezzo", "Val Gardena", "Tre Cime di Lavaredo", "Alpe di Siusi"],
        "tags": ["montagne", "randonnée", "nature", "UNESCO", "gastronomie"],
        "notes": "Paysages à couper le souffle. Randonnées accessibles.",
    },
    {
        "destination": "Lucerne et Suisse centrale",
        "country": "Suisse",
        "drive_hours": 2.0,
        "drive_km": 180,
        "seasons": ["printemps", "été", "automne"],
        "duration_days": [2, 3],
        "budget": "€€€",
        "highlights": ["Lucerne", "Pilatus", "Rigi", "Lac des Quatre-Cantons"],
        "tags": ["lac", "montagne", "culture", "trains panoramiques"],
        "notes": "Suisse = cher, à réserver pour une occasion spéciale.",
    },
    {
        "destination": "Alsace du Nord – Wissembourg",
        "country": "France",
        "drive_hours": 1.5,
        "drive_km": 130,
        "seasons": ["printemps", "automne"],
        "duration_days": [2, 3],
        "budget": "€",
        "highlights": ["Wissembourg", "Saverne", "Parc naturel Vosges du Nord", "Château du Haut-Barr"],
        "tags": ["patrimoine", "nature", "randonnée", "châteaux"],
    },
    {
        "destination": "Bourgogne – Dijon",
        "country": "France",
        "drive_hours": 2.5,
        "drive_km": 220,
        "seasons": ["automne", "printemps"],
        "duration_days": [3, 4],
        "budget": "€€",
        "highlights": ["Dijon", "Beaune", "Clos Vougeot", "Route des Grands Crus"],
        "tags": ["vin", "gastronomie", "patrimoine", "moutarde"],
        "notes": "Vendanges en automne, idéal septembre-octobre.",
    },
    {
        "destination": "Bruges et Gand",
        "country": "Belgique",
        "drive_hours": 5.5,
        "drive_km": 520,
        "seasons": ["printemps", "automne", "hiver"],
        "duration_days": [3, 4],
        "budget": "€€",
        "highlights": ["Bruges centre", "Gand", "chocolat", "bières belges"],
        "tags": ["culture", "gastronomie", "patrimoine", "canaux", "art flamand"],
    },
    {
        "destination": "Munich et Bavière",
        "country": "Allemagne",
        "drive_hours": 3.5,
        "drive_km": 340,
        "seasons": ["automne", "printemps", "été"],
        "duration_days": [3, 4],
        "budget": "€€",
        "highlights": ["Munich centre", "Neuschwanstein", "Starnberger See", "Zugspitze"],
        "tags": ["culture", "châteaux", "bière", "nature"],
        "notes": "Oktoberfest fin septembre. Châteaux de Louis II à 2h.",
    },
    {
        "destination": "Cinque Terre",
        "country": "Italie",
        "drive_hours": 5.0,
        "drive_km": 480,
        "seasons": ["printemps", "automne"],
        "duration_days": [4, 5],
        "budget": "€€",
        "highlights": ["Monterosso", "Vernazza", "Manarola", "Riomaggiore"],
        "tags": ["mer", "randonnée", "villages", "UNESCO", "gastronomie"],
        "notes": "Éviter l'été (surpeuplé). Train entre les villages.",
    },
    {
        "destination": "Provence – Luberon",
        "country": "France",
        "drive_hours": 5.5,
        "drive_km": 550,
        "seasons": ["printemps", "été"],
        "duration_days": [4, 5],
        "budget": "€€",
        "highlights": ["Gordes", "Roussillon", "Lavande", "Avignon"],
        "tags": ["nature", "villages", "lavande", "gastronomie", "soleil"],
        "notes": "Lavande en fleur mi-juin à mi-juillet.",
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


def _calculate_drive_score(hours: float) -> float:
    """Calcule le score trajet (0-1)."""
    if hours < 2:
        return 1.0
    elif hours < 3:
        return 0.8
    elif hours < 4:
        return 0.6
    elif hours < 5:
        return 0.4
    elif hours < 8:
        return 0.2
    else:
        return 0.1


def _calculate_season_score(trip: Dict, season: str) -> float:
    """Calcule le score saison (0-0.4)."""
    seasons = trip.get("seasons", [])

    if "all" in seasons:
        return 0.3
    elif season in seasons:
        return 0.4
    else:
        return 0.1  # Hors saison


def _calculate_preference_score(trip: Dict, profile: Dict) -> float:
    """
    Calcule le score préférences utilisateur (0-0.5).
    """
    score = 0.0
    tags = [t.lower() for t in trip.get("tags", [])]

    # Tags musicaux
    music_artists = profile.get("music_artists", [])
    for artist in music_artists:
        if artist.lower() in tags:
            score += 0.25
            break

    # Tags expos
    expo_artists = profile.get("expo_artists", [])
    for artist in expo_artists:
        if artist.lower() in tags:
            score += 0.2
            break

    # Tags généraux appréciés
    preferred_tags = ["gastronomie", "culture", "nature", "vin", "patrimoine"]
    matching_tags = sum(1 for pt in preferred_tags if pt in tags)
    score += min(matching_tags * 0.1, 0.3)

    return min(score, 0.5)


def _calculate_novelty_score(trip: Dict, seen_destinations: List[str]) -> float:
    """Calcule le score nouveauté."""
    destination = trip.get("destination", "").lower()

    for seen in seen_destinations:
        if destination in seen.lower() or seen.lower() in destination:
            return -0.3

    return 0.15


def _get_budget_estimate(trip: Dict) -> str:
    """Estime le budget total pour un roadtrip."""
    budget_symbol = trip.get("budget", "€€")
    duration = trip.get("duration_days", [3, 4])
    avg_duration = sum(duration) / len(duration)
    drive_km = trip.get("drive_km", 300)

    # Estimations
    fuel_cost = drive_km * 2 * 0.15  # Aller-retour, 0.15€/km
    estimates = {
        "€": {"hotel_night": 70, "daily": 50},
        "€€": {"hotel_night": 100, "daily": 70},
        "€€€": {"hotel_night": 150, "daily": 100},
    }

    est = estimates.get(budget_symbol, estimates["€€"])
    nights = avg_duration - 1
    total = fuel_cost + (est["hotel_night"] * nights) + (est["daily"] * avg_duration)

    return f"{total:.0f}€"


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def get_roadtrips(
    vacation_period: Dict,
    profile: Dict
) -> List[Dict]:
    """
    Récupère les roadtrips recommandés avec scoring.

    Args:
        vacation_period: Dict avec start, end, days, label
        profile: Dict avec music_artists, expo_artists, etc.

    Returns:
        Liste de roadtrips triés par travel_score
    """
    start_date = vacation_period.get("start")
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

    season = _get_current_season(start_date)

    # Destinations déjà visitées
    seen_destinations = profile.get("trips_seen_recent", [])

    results = []

    for trip in ROAD_TRIPS:
        # Score trajet
        drive_score = _calculate_drive_score(trip["drive_hours"])

        # Score saison
        season_score = _calculate_season_score(trip, season)

        # Score préférences
        preference_score = _calculate_preference_score(trip, profile)

        # Score nouveauté
        novelty_score = _calculate_novelty_score(trip, seen_destinations)

        # Score total
        travel_score = (
            drive_score * 0.30 +
            season_score * 0.30 +
            preference_score * 0.25 +
            novelty_score * 0.15
        )

        results.append({
            **trip,
            "transport": "voiture",
            "season": season,
            "drive_score": round(drive_score, 2),
            "season_score": round(season_score, 2),
            "preference_score": round(preference_score, 2),
            "novelty_score": round(novelty_score, 2),
            "travel_score": round(travel_score, 2),
            "budget_estimate": _get_budget_estimate(trip),
        })

    # Trier par travel_score décroissant
    results.sort(key=lambda r: r["travel_score"], reverse=True)

    print(f"  Roadtrips : {len(results)} destinations scorées")

    return results


def format_roadtrips_context(roadtrips: List[Dict], limit: int = 3) -> str:
    """Formate les roadtrips pour le contexte Claude."""
    if not roadtrips:
        return "Aucun roadtrip recommandé."

    lines = [f"Roadtrips en voiture ({len(roadtrips)} destinations) :"]

    for trip in roadtrips[:limit]:
        highlights = ", ".join(trip.get("highlights", [])[:3])

        lines.append(
            f"- {trip['destination']} ({trip['country']}) : "
            f"{trip['drive_hours']}h de route | score {trip['travel_score']:.2f}"
        )
        lines.append(f"  Highlights : {highlights}")
        if trip.get("notes"):
            lines.append(f"  Note : {trip['notes']}")

    return "\n".join(lines)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST COLLECTOR TRAVEL_ROADTRIPS")
    print("=" * 60)

    # Profil test
    test_profile = {
        "music_artists": ["The Cure", "Pulp", "Fontaines D.C."],
        "expo_artists": ["Soulages", "Klimt"],
        "trips_seen_recent": ["Forêt Noire"],
    }

    # Période test (automne)
    test_period = {
        "start": "2026-10-20",
        "end": "2026-10-27",
        "days": 7,
        "label": "Vacances de la Toussaint",
    }

    roadtrips = get_roadtrips(test_period, test_profile)

    print(f"\nSaison détectée : {roadtrips[0]['season'] if roadtrips else 'N/A'}")
    print(f"\nTop 5 roadtrips par travel_score :")

    for i, trip in enumerate(roadtrips[:5], 1):
        print(f"\n  {i}. {trip['destination']} ({trip['country']})")
        print(f"     Trajet : {trip['drive_hours']}h ({trip['drive_km']}km)")
        print(f"     Score total : {trip['travel_score']:.2f}")
        print(f"     - Trajet : {trip['drive_score']:.2f}")
        print(f"     - Saison : {trip['season_score']:.2f}")
        print(f"     - Préférences : {trip['preference_score']:.2f}")
        print(f"     - Nouveauté : {trip['novelty_score']:.2f}")
        print(f"     Budget estimé : {trip['budget_estimate']}")
