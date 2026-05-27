"""
Module de cache SQLite pour les collectors.
Réduit les appels réseau en stockant les résultats temporairement.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from engine.database import get_connection, DB_PATH


def _init_cache_table():
    """Crée la table cache si elle n'existe pas, avec index pour performance."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT,
            created_at DATETIME,
            expires_at DATETIME
        )
    """)

    # Index sur expires_at pour accélérer les lookups et le nettoyage
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON cache(expires_at)
    """)

    conn.commit()
    conn.close()


# Initialiser la table au premier import
_init_cache_table()


def cache_get(key: str) -> Optional[Any]:
    """
    Récupère une valeur du cache si elle existe et n'est pas expirée.

    Args:
        key: Clé du cache (ex: "weather_2026-05-23")

    Returns:
        La valeur désérialisée ou None si absente/expirée
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("""
        SELECT value FROM cache
        WHERE key = ? AND expires_at > ?
    """, (key, now))

    row = cursor.fetchone()
    conn.close()

    if row:
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return None

    return None


def cache_set(key: str, value: Any, ttl_minutes: int = 360) -> None:
    """
    Stocke une valeur dans le cache.

    Args:
        key: Clé du cache
        value: Valeur à stocker (sera sérialisée en JSON)
        ttl_minutes: Durée de vie en minutes (défaut: 6h)
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now()
    expires_at = now + timedelta(minutes=ttl_minutes)

    # Sérialiser la valeur
    # Gérer les dates qui ne sont pas JSON-sérialisables
    value_json = json.dumps(value, default=_json_serializer, ensure_ascii=False)

    cursor.execute("""
        INSERT INTO cache (key, value, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            created_at = excluded.created_at,
            expires_at = excluded.expires_at
    """, (key, value_json, now.isoformat(), expires_at.isoformat()))

    conn.commit()
    conn.close()


def cache_clear_expired() -> int:
    """
    Supprime les entrées expirées du cache.

    Returns:
        Nombre d'entrées supprimées
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    cursor.execute("SELECT COUNT(*) as count FROM cache WHERE expires_at <= ?", (now,))
    count = cursor.fetchone()["count"]

    cursor.execute("DELETE FROM cache WHERE expires_at <= ?", (now,))

    conn.commit()
    conn.close()

    return count


def cache_clear_all() -> int:
    """
    Vide entièrement le cache.

    Returns:
        Nombre d'entrées supprimées
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM cache")
    count = cursor.fetchone()["count"]

    cursor.execute("DELETE FROM cache")

    conn.commit()
    conn.close()

    return count


def cache_stats() -> Dict[str, Any]:
    """
    Retourne des statistiques sur le cache.

    Returns:
        Dict avec total, active, expired, size_bytes, entries
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()

    # Total entries
    cursor.execute("SELECT COUNT(*) as count FROM cache")
    total = cursor.fetchone()["count"]

    # Active entries
    cursor.execute("SELECT COUNT(*) as count FROM cache WHERE expires_at > ?", (now,))
    active = cursor.fetchone()["count"]

    # Expired entries
    expired = total - active

    # Taille estimée
    cursor.execute("SELECT SUM(LENGTH(value)) as size FROM cache")
    row = cursor.fetchone()
    size_bytes = row["size"] if row["size"] else 0

    # Liste des entrées actives
    cursor.execute("""
        SELECT key, created_at, expires_at, LENGTH(value) as size
        FROM cache
        WHERE expires_at > ?
        ORDER BY created_at DESC
    """, (now,))

    entries = []
    for row in cursor.fetchall():
        entries.append({
            "key": row["key"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "size_bytes": row["size"]
        })

    conn.close()

    return {
        "total": total,
        "active": active,
        "expired": expired,
        "size_bytes": size_bytes,
        "size_kb": round(size_bytes / 1024, 2) if size_bytes else 0,
        "entries": entries
    }


def _json_serializer(obj):
    """Sérialiseur JSON custom pour les types non standards."""
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    if hasattr(obj, '__dict__'):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# Durées de cache recommandées par collector (en minutes)
CACHE_TTL = {
    "weather": 180,      # 3h
    "cinema": 360,       # 6h
    "events": 360,       # 6h
    "hiking": 1440,      # 24h
    "exhibitions": 720,  # 12h
    "concerts": 360,     # 6h
    "discovery": 240,    # 4h
    "openagenda": 360,   # 6h
}
