"""
Module de collecte des deals et promotions voyage.
Agrège les offres spéciales des différentes sources.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from engine.cache import cache_get, cache_set, CACHE_TTL


@dataclass
class TravelDeal:
    """Représente une offre promotionnelle voyage."""

    type: str  # "flight", "hotel", "package"
    title: str
    destination: str
    destination_iata: Optional[str] = None
    price: float = 0.0
    normal_price: float = 0.0
    saving: float = 0.0
    saving_percent: float = 0.0
    provider: str = ""
    url: str = ""
    expires: Optional[date] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    description: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convertit en dictionnaire."""
        return {
            "type": self.type,
            "title": self.title,
            "destination": self.destination,
            "destination_iata": self.destination_iata,
            "price": self.price,
            "normal_price": self.normal_price,
            "saving": self.saving,
            "saving_percent": self.saving_percent,
            "provider": self.provider,
            "url": self.url,
            "expires": self.expires.isoformat() if self.expires else None,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "description": self.description,
            "metadata": self.metadata,
        }

    @property
    def is_valid(self) -> bool:
        """Vérifie si le deal est encore valide."""
        if self.expires and self.expires < date.today():
            return False
        return True

    @property
    def deal_score(self) -> float:
        """Calcule un score de qualité du deal (0-1)."""
        score = 0.0

        # Économie en pourcentage
        if self.saving_percent >= 50:
            score += 0.4
        elif self.saving_percent >= 30:
            score += 0.3
        elif self.saving_percent >= 20:
            score += 0.2
        elif self.saving_percent >= 10:
            score += 0.1

        # Prix absolu bas
        if self.price < 100:
            score += 0.3
        elif self.price < 200:
            score += 0.2
        elif self.price < 300:
            score += 0.1

        # Urgence (expire bientôt)
        if self.expires:
            days_left = (self.expires - date.today()).days
            if 0 < days_left <= 3:
                score += 0.2
            elif days_left <= 7:
                score += 0.1

        return min(score, 1.0)


# =============================================================================
# DEALS STATIQUES — Offres connues et récurrentes
# =============================================================================

RECURRING_DEALS = [
    {
        "type": "flight",
        "title": "Vols Ryanair - Vente flash",
        "destination": "Multiples",
        "provider": "Ryanair",
        "description": "Ventes flash régulières le mardi, vols dès 19.99€",
        "saving_percent": 30,
        "recurrence": "weekly",
    },
    {
        "type": "flight",
        "title": "EasyJet - Réservation anticipée",
        "destination": "Multiples",
        "provider": "EasyJet",
        "description": "Meilleurs prix 6-8 semaines avant le départ",
        "saving_percent": 25,
        "recurrence": "always",
    },
]


# =============================================================================
# FONCTIONS DE COLLECTE
# =============================================================================

def _fetch_ryanair_deals() -> List[TravelDeal]:
    """
    Récupère les deals Ryanair.

    Note: Ryanair n'a pas d'API publique pour les deals.
    On retourne des deals simulés basés sur les patterns connus.
    """
    deals = []

    # Vente flash du mardi
    today = date.today()
    if today.weekday() == 1:  # Mardi
        deals.append(TravelDeal(
            type="flight",
            title="Vente Flash Mardi - Ryanair",
            destination="Multiples destinations",
            price=29.99,
            normal_price=49.99,
            saving=20.00,
            saving_percent=40,
            provider="Ryanair",
            url="https://www.ryanair.com/fr/fr",
            expires=today + timedelta(days=1),
            description="Vols aller dès 29.99€ - Offre valable 24h",
        ))

    return deals


def _fetch_easyjet_deals() -> List[TravelDeal]:
    """
    Récupère les deals EasyJet.

    Note: EasyJet n'a pas d'API publique pour les deals.
    """
    deals = []

    # Offre early booking
    today = date.today()
    deals.append(TravelDeal(
        type="flight",
        title="Réservation anticipée EasyJet",
        destination="Multiples destinations",
        price=39.99,
        normal_price=59.99,
        saving=20.00,
        saving_percent=33,
        provider="EasyJet",
        url="https://www.easyjet.com/fr",
        valid_from=today,
        valid_to=today + timedelta(days=90),
        description="Économisez jusqu'à 33% en réservant 6-8 semaines à l'avance",
    ))

    return deals


def get_travel_deals(vacation_period: Optional[Dict] = None) -> List[TravelDeal]:
    """
    Récupère tous les deals voyage disponibles.

    Args:
        vacation_period: Dict avec start, end (optionnel, pour filtrer)

    Returns:
        Liste de TravelDeal triés par deal_score
    """
    cache_key = "travel_deals"

    # Vérifier le cache (4h pour les deals)
    cached = cache_get(cache_key)
    if cached:
        print("  Deals : CACHE HIT")
        deals = [TravelDeal(**d) if isinstance(d, dict) else d for d in cached]
    else:
        print("  Deals : collecte des offres...")

        deals = []
        deals.extend(_fetch_ryanair_deals())
        deals.extend(_fetch_easyjet_deals())

        # Cache 4h
        if deals:
            cache_set(cache_key, [d.to_dict() for d in deals], 240)

    # Filtrer les deals expirés
    valid_deals = [d for d in deals if d.is_valid]

    # Filtrer par période si fournie
    if vacation_period:
        start = vacation_period.get("start")
        end = vacation_period.get("end")

        if isinstance(start, str):
            start = datetime.strptime(start, "%Y-%m-%d").date()
        if isinstance(end, str):
            end = datetime.strptime(end, "%Y-%m-%d").date()

        filtered = []
        for deal in valid_deals:
            # Garder si le deal est valide pour la période
            if deal.valid_from and deal.valid_to:
                # Convertir les dates du deal si nécessaire (peut venir du cache)
                deal_from = deal.valid_from
                deal_to = deal.valid_to
                if isinstance(deal_from, str):
                    deal_from = datetime.strptime(deal_from, "%Y-%m-%d").date()
                if isinstance(deal_to, str):
                    deal_to = datetime.strptime(deal_to, "%Y-%m-%d").date()

                if deal_from <= end and deal_to >= start:
                    filtered.append(deal)
            else:
                filtered.append(deal)

        valid_deals = filtered

    # Trier par deal_score
    valid_deals.sort(key=lambda d: d.deal_score, reverse=True)

    print(f"  Deals : {len(valid_deals)} offres valides")

    return valid_deals


def format_deals_context(deals: List[TravelDeal], limit: int = 3) -> str:
    """Formate les deals pour le contexte Claude."""
    if not deals:
        return "Aucune offre spéciale en cours."

    lines = [f"Offres spéciales ({len(deals)} deals) :"]

    for deal in deals[:limit]:
        expire_str = f" (expire {deal.expires})" if deal.expires else ""
        saving_str = f"-{deal.saving_percent:.0f}%" if deal.saving_percent else ""

        lines.append(
            f"- {deal.title} : {deal.price:.0f}€ {saving_str}{expire_str}"
        )
        if deal.description:
            lines.append(f"  {deal.description}")

    return "\n".join(lines)


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST COLLECTOR TRAVEL_DEALS")
    print("=" * 60)

    deals = get_travel_deals()

    print(f"\n{len(deals)} deals trouvés")

    for i, deal in enumerate(deals[:5], 1):
        print(f"\n{i}. {deal.title}")
        print(f"   Prix : {deal.price:.0f}€ (normal: {deal.normal_price:.0f}€)")
        print(f"   Économie : {deal.saving:.0f}€ ({deal.saving_percent:.0f}%)")
        print(f"   Score : {deal.deal_score:.2f}")
