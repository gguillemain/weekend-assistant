"""
Provider Ryanair — API non officielle farfnd.
"""

import requests
from datetime import date, timedelta
from typing import List

from travel_providers.base import FlightProvider, FlightResult, ProviderRegistry


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
    "ATH": "Athens",
    "NAP": "Naples",
    "PSA": "Pisa",
    "VCE": "Venice",
}

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
    "ATH": "Grèce",
    "NAP": "Italie",
    "PSA": "Italie",
    "VCE": "Italie",
}

# Mapping des codes aéroports pour Ryanair
AIRPORT_CODES = {
    "BSL": "EAP",  # Basel-Mulhouse utilise EAP chez Ryanair
    "MLH": "EAP",
    "EAP": "EAP",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


class RyanairProvider(FlightProvider):
    """Provider Ryanair via API farfnd."""

    name = "Ryanair"
    enabled = True
    base_url = "https://www.ryanair.com/api/farfnd/3/oneWayFares"

    def search_flights(
        self,
        departure_airports: List[str],
        start_date: date,
        end_date: date,
        max_price: float = 150.0,
    ) -> List[FlightResult]:
        """Recherche des vols Ryanair."""
        results = []

        # Convertir les codes aéroports
        ryanair_airports = set()
        for airport in departure_airports:
            ryanair_code = AIRPORT_CODES.get(airport, airport)
            ryanair_airports.add(ryanair_code)

        for departure in ryanair_airports:
            # Recherche aller (premiers jours)
            outbound_results = self._search_one_way(
                departure,
                start_date,
                start_date + timedelta(days=3),
                max_price / 2,  # Max par trajet
            )

            # Recherche retour (derniers jours)
            return_results = self._search_one_way(
                departure,  # Note: pour le retour, on cherche vers le départ
                end_date - timedelta(days=3),
                end_date,
                max_price / 2,
            )

            # Combiner aller + retour
            return_by_dest = {r.destination_iata: r for r in return_results}

            for outbound in outbound_results:
                dest = outbound.destination_iata
                if dest in return_by_dest:
                    ret = return_by_dest[dest]
                    total_price = outbound.price + ret.price

                    if total_price <= max_price:
                        results.append(FlightResult(
                            destination=outbound.destination,
                            destination_iata=dest,
                            country=outbound.country,
                            departure_airport=departure,
                            price=total_price,
                            outbound_date=outbound.outbound_date,
                            return_date=ret.outbound_date,
                            airline=self.name,
                            direct=True,
                            url=self._build_url(departure, dest, outbound.outbound_date, ret.outbound_date),
                        ))

        return sorted(results, key=lambda r: r.price)

    def _search_one_way(
        self,
        departure: str,
        date_from: date,
        date_to: date,
        max_price: float,
    ) -> List[FlightResult]:
        """Recherche de vols aller simple."""
        params = {
            "departureAirportIataCode": departure,
            "outboundDepartureDateFrom": date_from.strftime("%Y-%m-%d"),
            "outboundDepartureDateTo": date_to.strftime("%Y-%m-%d"),
            "priceValueTo": int(max_price),
            "currency": "EUR",
        }

        try:
            response = requests.get(
                self.base_url,
                params=params,
                headers=HEADERS,
                timeout=15,
            )

            if response.status_code != 200:
                return []

            data = response.json()
            fares = data.get("fares", [])

            results = []
            for fare in fares:
                try:
                    outbound = fare.get("outbound", {})
                    dest_iata = outbound.get("arrivalAirport", {}).get("iataCode")
                    if not dest_iata:
                        continue

                    price = outbound.get("price", {}).get("value", 0)
                    dep_date = outbound.get("departureDate", "")[:10]

                    results.append(FlightResult(
                        destination=IATA_TO_CITY.get(dest_iata, dest_iata),
                        destination_iata=dest_iata,
                        country=IATA_TO_COUNTRY.get(dest_iata, "Europe"),
                        departure_airport=departure,
                        price=price,
                        outbound_date=dep_date,
                        airline=self.name,
                    ))
                except (KeyError, TypeError):
                    continue

            return results

        except requests.RequestException as e:
            print(f"  ⚠ Ryanair API error: {e}")
            return []

    def _build_url(self, departure: str, dest: str, outbound: str, return_date: str) -> str:
        """Construit l'URL de réservation Ryanair."""
        return (
            f"https://www.ryanair.com/fr/fr/trip/flights/select"
            f"?adults=2&teens=0&children=0&infants=0"
            f"&dateOut={outbound}&dateIn={return_date}"
            f"&originIata={departure}&destinationIata={dest}"
            f"&isReturn=true"
        )


# Enregistrer le provider
ProviderRegistry.register(RyanairProvider())
