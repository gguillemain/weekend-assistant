"""
Classes de base pour les fournisseurs de vols.
Architecture extensible : tout provider doit implémenter FlightProvider.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class FlightResult:
    """Résultat standardisé d'une recherche de vol."""

    destination: str
    destination_iata: str
    country: str
    departure_airport: str
    price: float
    outbound_date: str
    return_date: Optional[str] = None
    airline: str = ""
    direct: bool = True
    url: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convertit en dictionnaire."""
        return {
            "destination": self.destination,
            "destination_iata": self.destination_iata,
            "country": self.country,
            "departure_airport": self.departure_airport,
            "price": self.price,
            "outbound_date": self.outbound_date,
            "return_date": self.return_date,
            "airline": self.airline,
            "direct": self.direct,
            "url": self.url,
            "metadata": self.metadata,
        }


class FlightProvider(ABC):
    """
    Interface abstraite pour les fournisseurs de vols.

    Tout nouveau provider (Skyscanner, Google Flights, etc.)
    doit implémenter cette interface.
    """

    name: str = "BaseProvider"
    enabled: bool = True

    @abstractmethod
    def search_flights(
        self,
        departure_airports: List[str],
        start_date: date,
        end_date: date,
        max_price: float = 150.0,
    ) -> List[FlightResult]:
        """
        Recherche des vols depuis les aéroports de départ.

        Args:
            departure_airports: Liste des codes IATA (ex: ["BSL", "MLH"])
            start_date: Date de début de la période de voyage
            end_date: Date de fin de la période de voyage
            max_price: Prix maximum par trajet (défaut 150€)

        Returns:
            Liste de FlightResult triés par prix
        """
        pass

    def is_available(self) -> bool:
        """Vérifie si le provider est disponible (API accessible)."""
        return self.enabled

    def get_name(self) -> str:
        """Retourne le nom du provider."""
        return self.name


class ProviderRegistry:
    """Registre des providers de vols disponibles."""

    _providers: List[FlightProvider] = []

    @classmethod
    def register(cls, provider: FlightProvider) -> None:
        """Enregistre un nouveau provider."""
        cls._providers.append(provider)

    @classmethod
    def get_all(cls) -> List[FlightProvider]:
        """Retourne tous les providers enregistrés."""
        return [p for p in cls._providers if p.is_available()]

    @classmethod
    def search_all(
        cls,
        departure_airports: List[str],
        start_date: date,
        end_date: date,
        max_price: float = 150.0,
    ) -> List[FlightResult]:
        """
        Recherche sur tous les providers disponibles.

        Returns:
            Liste consolidée de résultats, dédupliquée par destination
        """
        all_results = []

        for provider in cls.get_all():
            try:
                results = provider.search_flights(
                    departure_airports, start_date, end_date, max_price
                )
                all_results.extend(results)
            except Exception as e:
                print(f"  ⚠ {provider.name} error: {e}")

        # Dédupliquer par destination (garder le moins cher)
        best_by_dest = {}
        for result in all_results:
            key = result.destination_iata
            if key not in best_by_dest or result.price < best_by_dest[key].price:
                best_by_dest[key] = result

        # Trier par prix
        return sorted(best_by_dest.values(), key=lambda r: r.price)
