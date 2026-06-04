"""
Module de collecte des vols low-cost depuis Basel-Mulhouse (EAP/BSL).
Interroge les APIs Ryanair et EasyJet pour détecter les vols pas chers.
"""

import requests
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from engine.cache import cache_get, cache_set, CACHE_TTL


# =============================================================================
# CONFIGURATION
# =============================================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# Aéroports de départ
DEPARTURE_AIRPORTS = {
    "ryanair": "EAP",  # EuroAirport code Ryanair
    "easyjet": "BSL",  # EuroAirport code EasyJet
}

# Estimation prix hôtel par nuit (2 personnes, budget)
HOTEL_ESTIMATES = {
    "London": 120,
    "Dublin": 90,
    "Edinburgh": 85,
    "Budapest": 55,
    "Prague": 60,
    "Vienna": 80,
    "Amsterdam": 95,
    "Barcelona": 85,
    "Rome": 80,
    "Lisbon": 70,
    "Copenhagen": 100,
    "Madrid": 75,
    "Brussels": 80,
    "Porto": 65,
    "Seville": 70,
    "Warsaw": 50,
    "Krakow": 45,
    "Valencia": 70,
    "Milan": 85,
    "Berlin": 75,
    "Marrakech": 60,
    "Faro": 65,
    "Malaga": 70,
    "Palma": 80,
    "default": 75,
}

# Mapping IATA -> nom ville
IATA_TO_CITY = {
    "LGW": "London", "STN": "London", "LTN": "London",
    "DUB": "Dublin",
    "EDI": "Edinburgh",
    "BUD": "Budapest",
    "PRG": "Prague",
    "VIE": "Vienna",
    "AMS": "Amsterdam",
    "BCN": "Barcelona",
    "FCO": "Rome", "CIA": "Rome",
    "LIS": "Lisbon",
    "CPH": "Copenhagen",
    "MAD": "Madrid",
    "BRU": "Brussels", "CRL": "Brussels",
    "OPO": "Porto",
    "SVQ": "Seville",
    "WAW": "Warsaw", "WMI": "Warsaw",
    "KRK": "Krakow",
    "VLC": "Valencia",
    "MXP": "Milan", "BGY": "Milan",
    "SXF": "Berlin", "BER": "Berlin",
    "RAK": "Marrakech",
    "FAO": "Faro",
    "AGP": "Malaga",
    "PMI": "Palma",
}

# Mapping IATA -> pays
IATA_TO_COUNTRY = {
    "LGW": "Royaume-Uni", "STN": "Royaume-Uni", "LTN": "Royaume-Uni",
    "DUB": "Irlande",
    "EDI": "Écosse",
    "BUD": "Hongrie",
    "PRG": "Tchéquie",
    "VIE": "Autriche",
    "AMS": "Pays-Bas",
    "BCN": "Espagne",
    "FCO": "Italie", "CIA": "Italie",
    "LIS": "Portugal",
    "CPH": "Danemark",
    "MAD": "Espagne",
    "BRU": "Belgique", "CRL": "Belgique",
    "OPO": "Portugal",
    "SVQ": "Espagne",
    "WAW": "Pologne", "WMI": "Pologne",
    "KRK": "Pologne",
    "VLC": "Espagne",
    "MXP": "Italie", "BGY": "Italie",
    "SXF": "Allemagne", "BER": "Allemagne",
    "RAK": "Maroc",
    "FAO": "Portugal",
    "AGP": "Espagne",
    "PMI": "Espagne",
}


# =============================================================================
# API RYANAIR
# =============================================================================

def _fetch_ryanair_fares(
    departure_date_from: str,
    departure_date_to: str,
    max_price: int = 150
) -> List[Dict]:
    """
    Récupère les vols Ryanair depuis EAP.

    API non officielle Ryanair farfnd.
    """
    base_url = "https://www.ryanair.com/api/farfnd/3/oneWayFares"

    params = {
        "departureAirportIataCode": DEPARTURE_AIRPORTS["ryanair"],
        "outboundDepartureDateFrom": departure_date_from,
        "outboundDepartureDateTo": departure_date_to,
        "priceValueTo": max_price,
        "currency": "EUR",
    }

    try:
        response = requests.get(
            base_url,
            params=params,
            headers=HEADERS,
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("fares", [])
        else:
            print(f"  ⚠ Ryanair API status {response.status_code}")
            return []

    except requests.RequestException as e:
        print(f"  ⚠ Erreur Ryanair API : {e}")
        return []


def _parse_ryanair_fares(fares: List[Dict], direction: str) -> Dict[str, Dict]:
    """
    Parse les vols Ryanair.

    Args:
        fares: Liste de fares Ryanair
        direction: "outbound" ou "return"

    Returns:
        Dict {destination_iata: {date, price, ...}}
    """
    results = {}

    for fare in fares:
        try:
            dest_iata = fare.get("outbound", {}).get("arrivalAirport", {}).get("iataCode")
            if not dest_iata:
                continue

            price = fare.get("outbound", {}).get("price", {}).get("value", 0)
            departure_date = fare.get("outbound", {}).get("departureDate", "")

            if dest_iata not in results or price < results[dest_iata]["price"]:
                results[dest_iata] = {
                    "iata": dest_iata,
                    "price": price,
                    "date": departure_date[:10] if departure_date else "",
                    "direction": direction,
                    "airline": "Ryanair",
                }

        except (KeyError, TypeError):
            continue

    return results


# =============================================================================
# API EASYJET
# =============================================================================

def _fetch_easyjet_fares(
    departure_date_from: str,
    departure_date_to: str
) -> List[Dict]:
    """
    Récupère les vols EasyJet depuis BSL.

    Note: L'API EasyJet est plus restrictive, on utilise un fallback.
    """
    base_url = "https://www.easyjet.com/api/routepricing/v2/search"

    params = {
        "departureIata": DEPARTURE_AIRPORTS["easyjet"],
        "currency": "EUR",
    }

    try:
        response = requests.get(
            base_url,
            params=params,
            headers={
                **HEADERS,
                "Origin": "https://www.easyjet.com",
                "Referer": "https://www.easyjet.com/",
            },
            timeout=15
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("routes", [])
        else:
            # EasyJet bloque souvent les requêtes API directes
            return []

    except requests.RequestException:
        return []


def _parse_easyjet_fares(routes: List[Dict]) -> Dict[str, Dict]:
    """Parse les vols EasyJet."""
    results = {}

    for route in routes:
        try:
            dest_iata = route.get("arrivalIata", "")
            price = route.get("price", {}).get("amount", 0)

            if dest_iata and price > 0:
                results[dest_iata] = {
                    "iata": dest_iata,
                    "price": price,
                    "date": "",  # EasyJet ne donne pas la date dans cette API
                    "direction": "outbound",
                    "airline": "EasyJet",
                }

        except (KeyError, TypeError):
            continue

    return results


# =============================================================================
# SCORING
# =============================================================================

def _calculate_budget_score(total_price: float) -> float:
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


def _estimate_hotel_price(city: str) -> float:
    """Estime le prix hôtel par nuit pour une ville."""
    return HOTEL_ESTIMATES.get(city, HOTEL_ESTIMATES["default"])


def _build_booking_url(airline: str, dest_iata: str, outbound_date: str, return_date: str) -> str:
    """Construit l'URL de réservation."""
    if airline == "Ryanair":
        return (
            f"https://www.ryanair.com/fr/fr/trip/flights/select"
            f"?adults=2&teens=0&children=0&infants=0"
            f"&dateOut={outbound_date}&dateIn={return_date}"
            f"&originIata={DEPARTURE_AIRPORTS['ryanair']}&destinationIata={dest_iata}"
            f"&isReturn=true"
        )
    else:
        return (
            f"https://www.easyjet.com/fr/booking/select-flights"
            f"?dep={DEPARTURE_AIRPORTS['easyjet']}&arr={dest_iata}"
            f"&out={outbound_date}&ret={return_date}&pax=2"
        )


# =============================================================================
# FONCTION PRINCIPALE
# =============================================================================

def get_cheap_flights(vacation_period: Dict) -> List[Dict]:
    """
    Récupère les vols pas chers depuis Basel-Mulhouse pour une période de vacances.

    Args:
        vacation_period: Dict avec start, end, label, days

    Returns:
        Liste de vols avec prix et scores
    """
    start_date = vacation_period.get("start")
    end_date = vacation_period.get("end")
    duration_days = vacation_period.get("days", 7)

    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

    # Clé de cache
    cache_key = f"flights_{start_date}_{end_date}"

    cached = cache_get(cache_key)
    if cached:
        print("  Vols : CACHE HIT")
        return cached

    print("  Vols : recherche Ryanair/EasyJet...")

    # Dates pour les recherches
    # Aller : premiers jours des vacances
    outbound_from = start_date.strftime("%Y-%m-%d")
    outbound_to = (start_date + timedelta(days=3)).strftime("%Y-%m-%d")

    # Retour : derniers jours des vacances
    return_from = (end_date - timedelta(days=3)).strftime("%Y-%m-%d")
    return_to = end_date.strftime("%Y-%m-%d")

    # Récupérer les vols aller Ryanair
    outbound_fares = _fetch_ryanair_fares(outbound_from, outbound_to, max_price=100)
    outbound_flights = _parse_ryanair_fares(outbound_fares, "outbound")

    # Récupérer les vols retour Ryanair
    return_fares = _fetch_ryanair_fares(return_from, return_to, max_price=100)
    return_flights = _parse_ryanair_fares(return_fares, "return")

    # Récupérer EasyJet (fallback)
    easyjet_routes = _fetch_easyjet_fares(outbound_from, outbound_to)
    easyjet_flights = _parse_easyjet_fares(easyjet_routes)

    # Combiner aller + retour
    flights = []

    # Ryanair : combiner aller et retour
    for dest_iata, outbound in outbound_flights.items():
        if dest_iata in return_flights:
            ret = return_flights[dest_iata]
            total_price = outbound["price"] + ret["price"]

            if total_price <= 150:
                city = IATA_TO_CITY.get(dest_iata, dest_iata)
                country = IATA_TO_COUNTRY.get(dest_iata, "Europe")
                hotel_per_night = _estimate_hotel_price(city)
                nights = duration_days - 1
                total_estimate = total_price + (hotel_per_night * nights)

                flights.append({
                    "destination": city,
                    "destination_iata": dest_iata,
                    "country": country,
                    "price_flight": total_price,
                    "outbound_date": outbound["date"],
                    "return_date": ret["date"],
                    "duration_days": duration_days,
                    "airline": "Ryanair",
                    "url": _build_booking_url("Ryanair", dest_iata, outbound["date"], ret["date"]),
                    "price_hotel_estimate": hotel_per_night,
                    "price_total_estimate": total_estimate,
                    "budget_score": _calculate_budget_score(total_estimate),
                })

    # EasyJet : estimations (API moins précise)
    for dest_iata, flight in easyjet_flights.items():
        # Éviter les doublons avec Ryanair
        if any(f["destination_iata"] == dest_iata for f in flights):
            continue

        # Estimer aller-retour (prix affiché * 2)
        estimated_price = flight["price"] * 2

        if estimated_price <= 150:
            city = IATA_TO_CITY.get(dest_iata, dest_iata)
            country = IATA_TO_COUNTRY.get(dest_iata, "Europe")
            hotel_per_night = _estimate_hotel_price(city)
            nights = duration_days - 1
            total_estimate = estimated_price + (hotel_per_night * nights)

            flights.append({
                "destination": city,
                "destination_iata": dest_iata,
                "country": country,
                "price_flight": estimated_price,
                "outbound_date": outbound_from,
                "return_date": return_to,
                "duration_days": duration_days,
                "airline": "EasyJet",
                "url": _build_booking_url("EasyJet", dest_iata, outbound_from, return_to),
                "price_hotel_estimate": hotel_per_night,
                "price_total_estimate": total_estimate,
                "budget_score": _calculate_budget_score(total_estimate),
            })

    # Trier par budget_score décroissant
    flights.sort(key=lambda f: f["budget_score"], reverse=True)

    print(f"  Vols : {len(flights)} destinations < 150€ A/R")

    # Cache 24h
    if flights:
        cache_set(cache_key, flights, CACHE_TTL.get("flights", 1440))

    return flights


def format_flights_context(flights: List[Dict], limit: int = 5) -> str:
    """Formate les vols pour le contexte Claude."""
    if not flights:
        return "Aucun vol pas cher trouvé depuis Basel-Mulhouse."

    lines = [f"Vols < 150€ A/R depuis BSL ({len(flights)} destinations) :"]

    for flight in flights[:limit]:
        lines.append(
            f"- {flight['destination']} ({flight['country']}) : "
            f"{flight['price_flight']:.0f}€ A/R {flight['airline']} | "
            f"Budget total estimé : {flight['price_total_estimate']:.0f}€"
        )

    return "\n".join(lines)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST COLLECTOR TRAVEL_FLIGHTS")
    print("=" * 60)

    # Simuler des vacances dans 2 semaines
    test_period = {
        "start": (date.today() + timedelta(days=14)).strftime("%Y-%m-%d"),
        "end": (date.today() + timedelta(days=21)).strftime("%Y-%m-%d"),
        "days": 7,
        "label": "Test vacances",
    }

    print(f"\nPériode : {test_period['start']} → {test_period['end']}")

    flights = get_cheap_flights(test_period)

    print(f"\n{len(flights)} vols trouvés")

    if flights:
        print("\nTop 5 par budget_score :")
        for i, f in enumerate(flights[:5], 1):
            print(f"  {i}. {f['destination']} ({f['airline']})")
            print(f"     Vol : {f['price_flight']:.0f}€ | Total estimé : {f['price_total_estimate']:.0f}€")
            print(f"     Score : {f['budget_score']}")
