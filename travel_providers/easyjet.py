"""
Provider EasyJet — API route pricing.
Note: L'API EasyJet est plus restrictive, ce provider est un fallback.
"""

import requests
from datetime import date
from typing import List

from travel_providers.base import FlightProvider, FlightResult, ProviderRegistry
from travel_providers.ryanair import IATA_TO_CITY, IATA_TO_COUNTRY


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Origin": "https://www.easyjet.com",
    "Referer": "https://www.easyjet.com/",
}


class EasyJetProvider(FlightProvider):
    """Provider EasyJet via API route pricing."""

    name = "EasyJet"
    enabled = True
    base_url = "https://www.easyjet.com/api/routepricing/v2/search"

    def search_flights(
        self,
        departure_airports: List[str],
        start_date: date,
        end_date: date,
        max_price: float = 150.0,
    ) -> List[FlightResult]:
        """
        Recherche des vols EasyJet.

        Note: L'API EasyJet est moins précise, elle retourne des prix
        indicatifs sans dates spécifiques.
        """
        results = []

        for departure in departure_airports:
            # EasyJet utilise BSL directement
            if departure in ("MLH", "EAP"):
                departure = "BSL"

            try:
                response = requests.get(
                    self.base_url,
                    params={
                        "departureIata": departure,
                        "currency": "EUR",
                    },
                    headers=HEADERS,
                    timeout=15,
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                routes = data.get("routes", [])

                for route in routes:
                    try:
                        dest_iata = route.get("arrivalIata", "")
                        price = route.get("price", {}).get("amount", 0)

                        if not dest_iata or price <= 0:
                            continue

                        # EasyJet donne un prix aller simple, on double pour A/R
                        total_price = price * 2

                        if total_price <= max_price:
                            results.append(FlightResult(
                                destination=IATA_TO_CITY.get(dest_iata, dest_iata),
                                destination_iata=dest_iata,
                                country=IATA_TO_COUNTRY.get(dest_iata, "Europe"),
                                departure_airport=departure,
                                price=total_price,
                                outbound_date=start_date.strftime("%Y-%m-%d"),
                                return_date=end_date.strftime("%Y-%m-%d"),
                                airline=self.name,
                                direct=True,
                                url=self._build_url(departure, dest_iata, start_date, end_date),
                                metadata={"estimated": True},
                            ))
                    except (KeyError, TypeError):
                        continue

            except requests.RequestException as e:
                print(f"  ⚠ EasyJet API error: {e}")

        return sorted(results, key=lambda r: r.price)

    def _build_url(self, departure: str, dest: str, start: date, end: date) -> str:
        """Construit l'URL de réservation EasyJet."""
        return (
            f"https://www.easyjet.com/fr/booking/select-flights"
            f"?dep={departure}&arr={dest}"
            f"&out={start.strftime('%Y-%m-%d')}&ret={end.strftime('%Y-%m-%d')}"
            f"&pax=2"
        )


# Enregistrer le provider
ProviderRegistry.register(EasyJetProvider())
