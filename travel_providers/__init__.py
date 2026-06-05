"""
Package travel_providers — Architecture extensible pour les fournisseurs de vols.
"""

from travel_providers.base import FlightProvider, FlightResult, ProviderRegistry
from travel_providers.ryanair import RyanairProvider
from travel_providers.easyjet import EasyJetProvider

__all__ = [
    "FlightProvider",
    "FlightResult",
    "ProviderRegistry",
    "RyanairProvider",
    "EasyJetProvider",
]
