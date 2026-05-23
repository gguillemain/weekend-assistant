from datetime import date, timedelta
from typing import List, Dict
import config


# Jours fériés français
JOURS_FERIES = {
    2024: [
        date(2024, 1, 1),   # Jour de l'an
        date(2024, 4, 1),   # Lundi de Pâques
        date(2024, 5, 1),   # Fête du travail
        date(2024, 5, 8),   # Victoire 1945
        date(2024, 5, 9),   # Ascension
        date(2024, 5, 20),  # Lundi de Pentecôte
        date(2024, 7, 14),  # Fête nationale
        date(2024, 8, 15),  # Assomption
        date(2024, 11, 1),  # Toussaint
        date(2024, 11, 11), # Armistice
        date(2024, 12, 25), # Noël
    ],
    2025: [
        date(2025, 1, 1),   # Jour de l'an
        date(2025, 4, 21),  # Lundi de Pâques
        date(2025, 5, 1),   # Fête du travail
        date(2025, 5, 8),   # Victoire 1945
        date(2025, 5, 29),  # Ascension
        date(2025, 6, 9),   # Lundi de Pentecôte
        date(2025, 7, 14),  # Fête nationale
        date(2025, 8, 15),  # Assomption
        date(2025, 11, 1),  # Toussaint
        date(2025, 11, 11), # Armistice
        date(2025, 12, 25), # Noël
    ],
    2026: [
        date(2026, 1, 1),   # Jour de l'an
        date(2026, 4, 6),   # Lundi de Pâques
        date(2026, 5, 1),   # Fête du travail
        date(2026, 5, 8),   # Victoire 1945
        date(2026, 5, 14),  # Ascension
        date(2026, 5, 25),  # Lundi de Pentecôte
        date(2026, 7, 14),  # Fête nationale
        date(2026, 8, 15),  # Assomption
        date(2026, 11, 1),  # Toussaint
        date(2026, 11, 11), # Armistice
        date(2026, 12, 25), # Noël
    ],
}

# Vacances scolaires Académie de Strasbourg (Zone B)
# Format: (début vacances après les cours, reprise des cours)
VACANCES_SCOLAIRES = {
    "2024-2025": {
        "toussaint": (date(2024, 10, 19), date(2024, 11, 4)),
        "noel": (date(2024, 12, 21), date(2025, 1, 6)),
        "hiver": (date(2025, 2, 22), date(2025, 3, 10)),
        "printemps": (date(2025, 4, 19), date(2025, 5, 5)),
        "ete": (date(2025, 7, 5), date(2025, 9, 1)),
    },
    "2025-2026": {
        "toussaint": (date(2025, 10, 18), date(2025, 11, 3)),
        "noel": (date(2025, 12, 20), date(2026, 1, 5)),
        "hiver": (date(2026, 2, 14), date(2026, 3, 2)),
        "printemps": (date(2026, 4, 11), date(2026, 4, 27)),
        "ete": (date(2026, 7, 4), date(2026, 9, 1)),
    },
}

VACANCES_LABELS = {
    "toussaint": "Vacances de la Toussaint",
    "noel": "Vacances de Noël",
    "hiver": "Vacances d'hiver",
    "printemps": "Vacances de printemps",
    "ete": "Vacances d'été",
}


def _get_all_holidays() -> List[date]:
    """Retourne tous les jours fériés de toutes les années."""
    all_holidays = []
    for year_holidays in JOURS_FERIES.values():
        all_holidays.extend(year_holidays)
    return all_holidays


def _is_weekend_day(d: date) -> bool:
    """Vérifie si un jour est un samedi ou dimanche."""
    return d.weekday() >= 5


def _is_holiday(d: date) -> bool:
    """Vérifie si un jour est férié."""
    return d in _get_all_holidays()


def _find_bridges(start_date: date, end_date: date) -> List[Dict]:
    """
    Trouve les ponts possibles entre deux dates.
    Un pont est un jour férié collé à un week-end.
    """
    bridges = []
    holidays = _get_all_holidays()

    for holiday in holidays:
        if holiday < start_date or holiday > end_date:
            continue

        weekday = holiday.weekday()

        # Jeudi férié -> pont le vendredi
        if weekday == 3:
            bridge_start = holiday
            bridge_end = holiday + timedelta(days=3)  # jusqu'au dimanche
            bridges.append({
                "type": "weekend",
                "label": f"Pont du {holiday.strftime('%d %B')}",
                "start": bridge_start,
                "end": bridge_end,
                "days": 4,
                "mode": "weekend"
            })

        # Mardi férié -> pont le lundi
        elif weekday == 1:
            bridge_start = holiday - timedelta(days=2)  # samedi
            bridge_end = holiday
            bridges.append({
                "type": "weekend",
                "label": f"Pont du {holiday.strftime('%d %B')}",
                "start": bridge_start,
                "end": bridge_end,
                "days": 4,
                "mode": "weekend"
            })

        # Vendredi férié -> week-end de 3 jours
        elif weekday == 4:
            bridge_start = holiday
            bridge_end = holiday + timedelta(days=2)  # dimanche
            bridges.append({
                "type": "weekend",
                "label": f"Week-end du {holiday.strftime('%d %B')}",
                "start": bridge_start,
                "end": bridge_end,
                "days": 3,
                "mode": "weekend"
            })

        # Lundi férié -> week-end de 3 jours
        elif weekday == 0:
            bridge_start = holiday - timedelta(days=2)  # samedi
            bridge_end = holiday
            bridges.append({
                "type": "weekend",
                "label": f"Week-end du {holiday.strftime('%d %B')}",
                "start": bridge_start,
                "end": bridge_end,
                "days": 3,
                "mode": "weekend"
            })

    return bridges


def _get_next_weekend(from_date: date) -> Dict:
    """Retourne le prochain week-end."""
    days_until_saturday = (5 - from_date.weekday()) % 7
    if days_until_saturday == 0 and from_date.weekday() != 5:
        days_until_saturday = 7

    saturday = from_date + timedelta(days=days_until_saturday)
    sunday = saturday + timedelta(days=1)

    return {
        "type": "weekend",
        "label": f"Week-end du {saturday.strftime('%d %B')}",
        "start": saturday,
        "end": sunday,
        "days": 2,
        "mode": "weekend"
    }


def _get_vacations(from_date: date) -> List[Dict]:
    """Retourne les périodes de vacances à venir."""
    vacations = []

    for school_year, periods in VACANCES_SCOLAIRES.items():
        for period_key, (start, end) in periods.items():
            if start >= from_date:
                vacations.append({
                    "type": "vacation",
                    "label": VACANCES_LABELS[period_key],
                    "start": start,
                    "end": end - timedelta(days=1),  # Dernier jour de vacances
                    "days": (end - start).days,
                    "mode": "vacances"
                })

    return sorted(vacations, key=lambda x: x["start"])


def _is_covered_by_vacation(period: Dict, vacations: List[Dict]) -> bool:
    """Vérifie si une période est entièrement couverte par des vacances."""
    for vacation in vacations:
        if period["start"] >= vacation["start"] and period["end"] <= vacation["end"]:
            return True
    return False


def get_next_periods(from_date: date = None, limit: int = 5) -> List[Dict]:
    """
    Retourne une liste des prochaines périodes (week-ends, ponts, vacances).

    Args:
        from_date: Date de départ (par défaut aujourd'hui)
        limit: Nombre maximum de périodes à retourner

    Returns:
        Liste de dictionnaires décrivant chaque période
    """
    if from_date is None:
        from_date = date.today()

    periods = []

    # Récupérer les vacances
    vacations = _get_vacations(from_date)
    periods.extend(vacations)

    # Ajouter les ponts pour les 6 prochains mois (hors vacances)
    end_date = from_date + timedelta(days=180)
    bridges = _find_bridges(from_date, end_date)
    for bridge in bridges:
        if not _is_covered_by_vacation(bridge, vacations):
            periods.append(bridge)

    # Ajouter les prochains week-ends (jusqu'à 8 semaines, hors vacances)
    current = from_date
    for _ in range(8):
        weekend = _get_next_weekend(current)
        if not _is_covered_by_vacation(weekend, vacations):
            periods.append(weekend)
        current = weekend["end"] + timedelta(days=1)

    # Trier par date de début et limiter
    periods = sorted(periods, key=lambda x: x["start"])

    # Supprimer les doublons (même date de début)
    seen_starts = set()
    unique_periods = []
    for period in periods:
        if period["start"] not in seen_starts:
            seen_starts.add(period["start"])
            unique_periods.append(period)

    return unique_periods[:limit]


def is_vacation_coming_soon(from_date: date = None) -> bool:
    """
    Vérifie si des vacances commencent dans moins de VACATION_SEND_DAYS_BEFORE jours.

    Returns:
        True si des vacances approchent, False sinon
    """
    if from_date is None:
        from_date = date.today()

    threshold = from_date + timedelta(days=config.VACATION_SEND_DAYS_BEFORE)

    vacations = _get_vacations(from_date)

    for vacation in vacations:
        if vacation["start"] <= threshold:
            return True

    return False


def get_next_period() -> Dict:
    """Retourne la prochaine période (pour affichage au démarrage)."""
    periods = get_next_periods(limit=1)
    return periods[0] if periods else None
