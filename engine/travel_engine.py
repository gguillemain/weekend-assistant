"""
Moteur de génération de suggestions de voyage — Architecture extensible.

Phases de recommandation :
- INSPIRATION (J-90+) : Découvrir des destinations
- OPPORTUNITIES (J-60 à J-90) : Détecter les bonnes affaires
- BOOKING (J-30 à J-60) : Recommander la réservation
- LAST_CALL (J-0 à J-30) : Dernière suggestion
"""

import json
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import anthropic

import config
from travel_providers import ProviderRegistry, FlightResult
from travel_providers.ryanair import RyanairProvider  # Force l'enregistrement
from travel_providers.easyjet import EasyJetProvider  # Force l'enregistrement
from collectors.travel_citybreaks import get_citybreaks, CITY_BREAKS
from collectors.travel_roadtrips import get_roadtrips, ROAD_TRIPS
from collectors.travel_deals import get_travel_deals, TravelDeal
from engine.profile import get_profile, get_activity_stats


# =============================================================================
# PHASES DE VOYAGE
# =============================================================================

def get_travel_phase(days_before_vacation: int) -> str:
    """
    Détermine la phase de recommandation voyage.

    Args:
        days_before_vacation: Nombre de jours avant les vacances

    Returns:
        "INSPIRATION", "OPPORTUNITIES", "BOOKING", ou "LAST_CALL"
    """
    if days_before_vacation >= 90:
        return "INSPIRATION"
    elif days_before_vacation >= 60:
        return "OPPORTUNITIES"
    elif days_before_vacation >= 30:
        return "BOOKING"
    else:
        return "LAST_CALL"


def get_phase_config(phase: str) -> Dict:
    """Retourne la configuration pour une phase donnée."""
    configs = {
        "INSPIRATION": {
            "search_flights": False,
            "show_prices": False,
            "focus": "découverte",
            "message": "Commencez à rêver à vos prochaines vacances",
            "limit_citybreaks": 5,
            "limit_roadtrips": 4,
        },
        "OPPORTUNITIES": {
            "search_flights": True,
            "show_prices": True,
            "focus": "bonnes_affaires",
            "message": "C'est le moment de repérer les bonnes affaires",
            "limit_citybreaks": 4,
            "limit_roadtrips": 3,
        },
        "BOOKING": {
            "search_flights": True,
            "show_prices": True,
            "focus": "réservation",
            "message": "C'est probablement le bon moment pour réserver",
            "limit_citybreaks": 3,
            "limit_roadtrips": 3,
            "booking_recommendation": True,
        },
        "LAST_CALL": {
            "search_flights": True,
            "show_prices": True,
            "focus": "dernière_minute",
            "message": "Dernière ligne droite avant les vacances",
            "limit_citybreaks": 3,
            "limit_roadtrips": 2,
            "quick_destinations_only": True,
        },
    }
    return configs.get(phase, configs["INSPIRATION"])


# =============================================================================
# SCORING
# =============================================================================

def calculate_availability_score(
    destination_duration: List[int],
    vacation_days: int
) -> float:
    """
    Calcule le score de compatibilité durée (0-1).

    Args:
        destination_duration: [min_days, max_days] recommandés
        vacation_days: Durée des vacances

    Returns:
        Score entre 0 et 1
    """
    min_days, max_days = destination_duration

    if min_days <= vacation_days <= max_days:
        return 1.0
    elif vacation_days >= min_days - 1 and vacation_days <= max_days + 1:
        return 0.8
    elif vacation_days >= min_days - 2 and vacation_days <= max_days + 2:
        return 0.5
    else:
        return 0.2


def calculate_budget_score(total_price: float) -> float:
    """Calcule le score budget (0-1)."""
    if total_price < 500:
        return 1.0
    elif total_price < 700:
        return 0.8
    elif total_price < 900:
        return 0.6
    elif total_price < 1200:
        return 0.4
    else:
        return 0.2


def calculate_travel_score(
    budget_score: float,
    season_score: float,
    preference_score: float,
    novelty_score: float,
    availability_score: float,
    is_roadtrip: bool = False
) -> float:
    """
    Calcule le score total de voyage.

    Formule :
    - budget_score (ou drive_score) × 0.30
    - season_score × 0.25
    - preference_score × 0.20
    - novelty_score × 0.10
    - availability_score × 0.15
    """
    return (
        budget_score * 0.30 +
        season_score * 0.25 +
        preference_score * 0.20 +
        novelty_score * 0.10 +
        availability_score * 0.15
    )


# =============================================================================
# COLLECTE DES DONNÉES
# =============================================================================

def search_flights(
    vacation_period: Dict,
    max_price: float = 150.0
) -> List[Dict]:
    """
    Recherche des vols via tous les providers enregistrés.

    Args:
        vacation_period: Dict avec start, end
        max_price: Prix maximum A/R

    Returns:
        Liste de vols consolidée
    """
    start = vacation_period.get("start")
    end = vacation_period.get("end")

    if isinstance(start, str):
        start = datetime.strptime(start, "%Y-%m-%d").date()
    if isinstance(end, str):
        end = datetime.strptime(end, "%Y-%m-%d").date()

    print(f"  Vols : recherche via {len(ProviderRegistry.get_all())} providers...")

    results = ProviderRegistry.search_all(
        departure_airports=config.HOME_AIRPORTS,
        start_date=start,
        end_date=end,
        max_price=max_price,
    )

    # Convertir en dicts avec estimations
    flights = []
    vacation_days = (end - start).days

    for result in results:
        hotel_per_night = config.HOTEL_ESTIMATES.get(
            result.destination,
            config.HOTEL_ESTIMATES["default"]
        )
        nights = vacation_days - 1
        total_estimate = result.price + (hotel_per_night * nights)

        flights.append({
            "destination": result.destination,
            "destination_iata": result.destination_iata,
            "country": result.country,
            "price_flight": result.price,
            "outbound_date": result.outbound_date,
            "return_date": result.return_date,
            "airline": result.airline,
            "url": result.url,
            "price_hotel_estimate": hotel_per_night,
            "price_total_estimate": total_estimate,
            "budget_score": calculate_budget_score(total_estimate),
        })

    print(f"  Vols : {len(flights)} destinations < {max_price}€ A/R")

    return flights


def enrich_citybreaks_with_flights(
    citybreaks: List[Dict],
    flights: List[Dict],
    vacation_days: int
) -> List[Dict]:
    """
    Enrichit les city-breaks avec les infos de vol et recalcule les scores.
    """
    flights_by_dest = {}
    for flight in flights:
        dest = flight["destination"].lower()
        if dest not in flights_by_dest or flight["budget_score"] > flights_by_dest[dest]["budget_score"]:
            flights_by_dest[dest] = flight

    for city in citybreaks:
        dest_lower = city["destination"].lower()

        # Score disponibilité
        duration = city.get("duration_days", [4, 5])
        availability_score = calculate_availability_score(duration, vacation_days)
        city["availability_score"] = round(availability_score, 2)

        # Info vol si disponible
        if dest_lower in flights_by_dest:
            flight = flights_by_dest[dest_lower]
            city["flight_info"] = {
                "price": flight["price_flight"],
                "airline": flight["airline"],
                "total_estimate": flight["price_total_estimate"],
            }
            city["budget_score"] = flight["budget_score"]
        else:
            city["budget_score"] = city.get("budget_score", 0.5)

        # Recalculer travel_score avec availability
        city["travel_score"] = round(calculate_travel_score(
            budget_score=city.get("budget_score", 0.5),
            season_score=city.get("season_score", 0.3),
            preference_score=city.get("preference_score", 0),
            novelty_score=city.get("novelty_score", 0.15),
            availability_score=availability_score,
        ), 2)

    # Retrier par travel_score
    citybreaks.sort(key=lambda c: c["travel_score"], reverse=True)

    return citybreaks


def enrich_roadtrips_with_availability(
    roadtrips: List[Dict],
    vacation_days: int
) -> List[Dict]:
    """
    Enrichit les roadtrips avec le score de disponibilité.
    """
    for trip in roadtrips:
        duration = trip.get("duration_days", [3, 4])
        availability_score = calculate_availability_score(duration, vacation_days)
        trip["availability_score"] = round(availability_score, 2)

        # Recalculer travel_score
        trip["travel_score"] = round(calculate_travel_score(
            budget_score=trip.get("drive_score", 0.5),
            season_score=trip.get("season_score", 0.3),
            preference_score=trip.get("preference_score", 0),
            novelty_score=trip.get("novelty_score", 0.15),
            availability_score=availability_score,
            is_roadtrip=True,
        ), 2)

    roadtrips.sort(key=lambda r: r["travel_score"], reverse=True)

    return roadtrips


# =============================================================================
# GÉNÉRATION DE PROMPT
# =============================================================================

PHASE_PROMPTS = {
    "INSPIRATION": """Tu es un conseiller voyage inspirant pour un couple d'enseignants
alsaciens (50 ans, Guebwiller). L'objectif est de leur faire DÉCOUVRIR des destinations,
pas de les pousser à réserver. Ton ton est enthousiaste et rêveur.

Profil : culture, musique (The Cure, Fontaines D.C.), art contemporain, gastronomie.
Géraldine adore Londres. Budget raisonnable.

NE PAS mentionner les prix précis. Focus sur l'expérience et les découvertes possibles.""",

    "OPPORTUNITIES": """Tu es un conseiller voyage pour un couple d'enseignants alsaciens
(50 ans, Guebwiller). L'objectif est de repérer les BONNES AFFAIRES.

Profil : culture, musique (The Cure, Fontaines D.C.), art contemporain, gastronomie.
Géraldine adore Londres. Budget raisonnable, aéroport Basel-Mulhouse.

Met en avant le rapport qualité-prix. Indique les prix et les économies potentielles.""",

    "BOOKING": """Tu es un conseiller voyage pour un couple d'enseignants alsaciens
(50 ans, Guebwiller). L'objectif est de les aider à RÉSERVER.

Profil : culture, musique (The Cure, Fontaines D.C.), art contemporain, gastronomie.
Géraldine adore Londres. Budget raisonnable, aéroport Basel-Mulhouse.

Pour les meilleures offres, indique clairement "C'est probablement le bon moment pour réserver."
Donne des conseils pratiques de réservation.""",

    "LAST_CALL": """Tu es un conseiller voyage pour un couple d'enseignants alsaciens
(50 ans, Guebwiller). Les vacances approchent, c'est la DERNIÈRE LIGNE DROITE.

Profil : culture, musique (The Cure, Fontaines D.C.), art contemporain, gastronomie.
Budget raisonnable, aéroport Basel-Mulhouse.

Focus sur les destinations accessibles rapidement : Londres, Prague, Forêt Noire, Salzbourg.
Évite les destinations qui demandent beaucoup d'organisation.""",
}


def build_travel_prompt(
    phase: str,
    vacation_period: Dict,
    flights: List[Dict],
    citybreaks: List[Dict],
    roadtrips: List[Dict],
    deals: List[TravelDeal],
    phase_config: Dict,
) -> str:
    """Construit le prompt utilisateur adapté à la phase."""

    start = vacation_period.get("start")
    end = vacation_period.get("end")
    days = vacation_period.get("days", 7)
    label = vacation_period.get("label", "Vacances")

    # Header
    lines = [
        f"Vacances : {label}",
        f"Du {start} au {end} ({days} jours)",
        f"Phase : {phase} — {phase_config['message']}",
        "",
    ]

    # Vols (si phase le permet)
    if phase_config.get("search_flights") and flights:
        lines.append(f"Vols trouvés < 150€ A/R depuis Basel-Mulhouse ({len(flights)}) :")
        for flight in flights[:5]:
            lines.append(
                f"- {flight['destination']} ({flight['country']}) : "
                f"{flight['price_flight']:.0f}€ A/R {flight['airline']} | "
                f"Budget total estimé : {flight['price_total_estimate']:.0f}€"
            )
        lines.append("")

    # Deals
    if deals:
        lines.append("Offres spéciales :")
        for deal in deals[:3]:
            lines.append(f"- {deal.title} : {deal.price:.0f}€ (-{deal.saving_percent:.0f}%)")
        lines.append("")

    # City-breaks
    limit_cb = phase_config.get("limit_citybreaks", 4)
    lines.append(f"City-breaks recommandés (top {limit_cb}) :")
    for city in citybreaks[:limit_cb]:
        flight_str = ""
        if city.get("flight_info") and phase_config.get("show_prices"):
            fi = city["flight_info"]
            flight_str = f" | Vol {fi['airline']} : {fi['price']:.0f}€ A/R"

        lines.append(
            f"- {city['destination']} ({city['country']}) : "
            f"score {city['travel_score']:.2f}{flight_str}"
        )
        if city.get("geraldine_loves"):
            lines.append("  ❤️ Géraldine adore")
        if city.get("notes"):
            lines.append(f"  Note : {city['notes']}")
    lines.append("")

    # Roadtrips
    limit_rt = phase_config.get("limit_roadtrips", 3)
    lines.append(f"Roadtrips recommandés (top {limit_rt}) :")
    for trip in roadtrips[:limit_rt]:
        highlights = ", ".join(trip.get("highlights", [])[:3])
        lines.append(
            f"- {trip['destination']} ({trip['country']}) : "
            f"{trip['drive_hours']}h de route | score {trip['travel_score']:.2f}"
        )
        lines.append(f"  Highlights : {highlights}")
    lines.append("")

    # Instruction finale
    lines.append("---")
    lines.append("")
    lines.append("Propose 3 à 4 suggestions de voyage adaptées à cette phase.")
    lines.append("")
    lines.append("Réponds UNIQUEMENT avec un tableau JSON valide :")
    lines.append('[{"destination": "...", "country": "...", "transport": "avion|voiture", ')
    lines.append('"duration_days": 4, "budget_total": "800€", ')
    lines.append('"highlights": ["...", "..."], "why_now": "...", ')
    lines.append('"booking_recommendation": true|false, "practical_tip": "..."}]')

    return "\n".join(lines)


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def generate_travel_suggestions(
    vacation_period: Dict,
    profile: Optional[Dict] = None
) -> Dict:
    """
    Génère des suggestions de voyage adaptées à la phase.

    Args:
        vacation_period: Dict avec start, end, days, label
        profile: Dict profil utilisateur (optionnel)

    Returns:
        Dict avec phase, days_before_vacation, flights_found, deals_found, suggestions
    """
    print("\n" + "=" * 50)
    print("GÉNÉRATION SUGGESTIONS VOYAGE")
    print("=" * 50)

    # Récupérer le profil si non fourni
    if profile is None:
        profile = get_profile()
        stats = get_activity_stats()
        profile["trips_seen_recent"] = stats.get("trips_seen_recent", [])

    # Calculer les jours avant vacances
    start = vacation_period.get("start")
    if isinstance(start, str):
        start = datetime.strptime(start, "%Y-%m-%d").date()

    days_before = (start - date.today()).days
    vacation_days = vacation_period.get("days", 7)

    # Déterminer la phase
    phase = get_travel_phase(days_before)
    phase_config = get_phase_config(phase)

    print(f"\n  Phase : {phase} (J-{days_before})")
    print(f"  Focus : {phase_config['focus']}")

    # Collecter les données
    print("\n1. Collecte des données...")

    # Vols (seulement si la phase le requiert)
    flights = []
    if phase_config.get("search_flights"):
        flights = search_flights(vacation_period)

    # Deals
    deals = get_travel_deals(vacation_period)

    # City-breaks et roadtrips
    citybreaks = get_citybreaks(vacation_period, flights, profile)
    roadtrips = get_roadtrips(vacation_period, profile)

    # Enrichir avec availability_score
    citybreaks = enrich_citybreaks_with_flights(citybreaks, flights, vacation_days)
    roadtrips = enrich_roadtrips_with_availability(roadtrips, vacation_days)

    # Filtrer pour LAST_CALL
    if phase_config.get("quick_destinations_only"):
        quick_destinations = {"londres", "london", "prague", "salzbourg", "salzburg"}
        quick_roadtrips = {"forêt noire", "alsace du nord", "lucerne"}

        citybreaks = [c for c in citybreaks
                      if c["destination"].lower() in quick_destinations
                      or c.get("duration_days", [5, 5])[0] <= 4][:3]

        roadtrips = [r for r in roadtrips
                     if r["destination"].lower() in quick_roadtrips
                     or r["drive_hours"] <= 3][:2]

    print(f"\n   Vols : {len(flights)}")
    print(f"   Deals : {len(deals)}")
    print(f"   City-breaks : {len(citybreaks)}")
    print(f"   Roadtrips : {len(roadtrips)}")

    # Construire le prompt
    print("\n2. Génération via Claude API...")

    system_prompt = PHASE_PROMPTS.get(phase, PHASE_PROMPTS["INSPIRATION"])
    user_prompt = build_travel_prompt(
        phase, vacation_period, flights, citybreaks, roadtrips, deals, phase_config
    )

    # Appeler Claude
    suggestions = []
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        response_text = response.content[0].text
        suggestions = _parse_response(response_text)

        print(f"   {len(suggestions)} suggestions générées")

    except Exception as e:
        print(f"   ⚠ Erreur Claude API : {e}")

    # Construire le résultat
    result = {
        "phase": phase,
        "phase_message": phase_config["message"],
        "days_before_vacation": days_before,
        "vacation_period": vacation_period,
        "flights_found": len(flights),
        "deals_found": len(deals),
        # Vols bruts pour le ticker (top 5 par budget_score)
        "flights": sorted(flights, key=lambda f: -f.get("budget_score", 0))[:5],
        "citybreaks_top": [
            {
                "destination": c["destination"],
                "country": c["country"],
                "travel_score": c["travel_score"],
                "availability_score": c.get("availability_score", 0),
                "geraldine_loves": c.get("geraldine_loves", False),
                "flight_info": c.get("flight_info"),
                "duration_days": c.get("duration_days", [4, 5]),
                "highlights": c.get("highlights", []),
                "budget": c.get("budget", "€€"),
                "seasons": c.get("seasons", ["all"]),
            }
            for c in citybreaks[:5]
        ],
        "roadtrips_top": [
            {
                "destination": r["destination"],
                "country": r["country"],
                "drive_hours": r["drive_hours"],
                "travel_score": r["travel_score"],
                "availability_score": r.get("availability_score", 0),
                "duration_days": r.get("duration_days", [3, 4]),
                "highlights": r.get("highlights", []),
                "best_season": r.get("seasons", ["été"])[0] if r.get("seasons") and r.get("seasons") != ["all"] else "toute saison",
            }
            for r in roadtrips[:5]
        ],
        "suggestions": suggestions,
        "generated_at": datetime.now().isoformat(),
    }

    print("\n" + "=" * 50)

    return result


def _parse_response(response_text: str) -> List[Dict]:
    """Parse la réponse JSON de Claude."""
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and "suggestions" in result:
            return result["suggestions"]
        return [result]
    except json.JSONDecodeError as e:
        print(f"  ⚠ Erreur parsing JSON : {e}")
        return []


# =============================================================================
# SCHEDULER HELPERS
# =============================================================================

def get_email_phase_for_vacation(days_before: int) -> Optional[str]:
    """
    Détermine si un email doit être envoyé pour cette phase.

    Returns:
        Phase à utiliser pour l'email, ou None si pas d'envoi
    """
    # Envoyer un email à J-90, J-60, J-30, J-14
    if days_before == 90:
        return "INSPIRATION"
    elif days_before == 60:
        return "OPPORTUNITIES"
    elif days_before == 30:
        return "BOOKING"
    elif days_before == 14:
        return "LAST_CALL"
    return None


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    from datetime import timedelta

    print("=" * 60)
    print("TEST TRAVEL ENGINE — ARCHITECTURE REFACTORÉE")
    print("=" * 60)

    # Test des phases
    print("\n1. Test des phases :")
    for days in [120, 90, 75, 60, 45, 30, 20, 14, 7]:
        phase = get_travel_phase(days)
        print(f"   J-{days:3d} → {phase}")

    # Test avec vacances simulées
    print("\n2. Test génération :")

    test_period = {
        "start": (date.today() + timedelta(days=45)).strftime("%Y-%m-%d"),
        "end": (date.today() + timedelta(days=52)).strftime("%Y-%m-%d"),
        "days": 7,
        "label": "Vacances test (J-45)",
    }

    test_profile = {
        "music_artists": ["The Cure", "Fontaines D.C."],
        "expo_artists": ["Soulages", "Klimt"],
        "trips_seen_recent": [],
    }

    result = generate_travel_suggestions(test_period, test_profile)

    print(f"\n   Phase : {result['phase']}")
    print(f"   Vols trouvés : {result['flights_found']}")
    print(f"   Suggestions : {len(result['suggestions'])}")

    if result["citybreaks_top"]:
        print("\n   Top city-breaks :")
        for cb in result["citybreaks_top"][:3]:
            print(f"   - {cb['destination']} : score {cb['travel_score']}")
