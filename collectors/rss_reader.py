import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional
import re


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}

# Namespaces courants dans les flux RSS/Atom
NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/"
}


def fetch_rss(url: str, timeout: int = 10) -> List[Dict]:
    """
    Parse un flux RSS/Atom et retourne une liste de dicts.

    Args:
        url: URL du flux RSS/Atom
        timeout: Timeout en secondes

    Returns:
        Liste de dicts avec title, description, link, published, categories
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()

        # Parser le XML
        root = ET.fromstring(response.content)

        # Détecter le type de flux
        if root.tag == "rss" or root.tag.endswith("}rss"):
            return _parse_rss(root)
        elif "feed" in root.tag.lower() or root.tag == "{http://www.w3.org/2005/Atom}feed":
            return _parse_atom(root)
        else:
            # Tenter RSS par défaut
            return _parse_rss(root)

    except requests.exceptions.RequestException as e:
        return []
    except ET.ParseError as e:
        return []
    except Exception as e:
        return []


def _parse_rss(root: ET.Element) -> List[Dict]:
    """Parse un flux RSS 2.0."""
    items = []

    # Trouver le channel
    channel = root.find("channel")
    if channel is None:
        channel = root

    # Parcourir les items
    for item in channel.findall("item"):
        entry = {
            "title": _get_text(item, "title"),
            "description": _clean_html(_get_text(item, "description")),
            "link": _get_text(item, "link"),
            "published": _parse_date(_get_text(item, "pubDate")),
            "categories": []
        }

        # Catégories
        for cat in item.findall("category"):
            if cat.text:
                entry["categories"].append(cat.text.strip())

        # Dublin Core date si pubDate absent
        if not entry["published"]:
            dc_date = _get_text(item, "dc:date", NAMESPACES.get("dc"))
            if dc_date:
                entry["published"] = _parse_date(dc_date)

        if entry["title"]:
            items.append(entry)

    return items


def _parse_atom(root: ET.Element) -> List[Dict]:
    """Parse un flux Atom."""
    items = []

    # Namespace Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # Trouver les entries
    entries = root.findall("atom:entry", ns)
    if not entries:
        entries = root.findall("entry")
    if not entries:
        # Essayer sans namespace
        entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for entry_elem in entries:
        entry = {
            "title": _get_text_atom(entry_elem, "title", ns),
            "description": _clean_html(_get_text_atom(entry_elem, "summary", ns) or
                                       _get_text_atom(entry_elem, "content", ns)),
            "link": _get_link_atom(entry_elem, ns),
            "published": _parse_date(_get_text_atom(entry_elem, "published", ns) or
                                     _get_text_atom(entry_elem, "updated", ns)),
            "categories": []
        }

        # Catégories
        for cat in entry_elem.findall("atom:category", ns):
            term = cat.get("term") or cat.get("label")
            if term:
                entry["categories"].append(term)

        # Sans namespace
        for cat in entry_elem.findall("category"):
            term = cat.get("term") or cat.get("label") or cat.text
            if term:
                entry["categories"].append(term)

        if entry["title"]:
            items.append(entry)

    return items


def _get_text(element: ET.Element, tag: str, namespace: str = None) -> str:
    """Récupère le texte d'un élément enfant."""
    if namespace:
        child = element.find(f"{{{namespace}}}{tag}")
    else:
        child = element.find(tag)

    if child is not None and child.text:
        return child.text.strip()
    return ""


def _get_text_atom(element: ET.Element, tag: str, ns: dict) -> str:
    """Récupère le texte d'un élément Atom."""
    # Avec namespace
    child = element.find(f"atom:{tag}", ns)
    if child is not None:
        return (child.text or "").strip()

    # Sans namespace
    child = element.find(tag)
    if child is not None:
        return (child.text or "").strip()

    # Namespace explicite
    child = element.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    if child is not None:
        return (child.text or "").strip()

    return ""


def _get_link_atom(element: ET.Element, ns: dict) -> str:
    """Récupère le lien d'un élément Atom."""
    # Chercher link avec rel="alternate" ou sans rel
    for link in element.findall("atom:link", ns):
        rel = link.get("rel", "alternate")
        if rel == "alternate":
            return link.get("href", "")

    for link in element.findall("link"):
        rel = link.get("rel", "alternate")
        if rel == "alternate":
            return link.get("href", "")

    for link in element.findall("{http://www.w3.org/2005/Atom}link"):
        rel = link.get("rel", "alternate")
        if rel == "alternate":
            return link.get("href", "")

    # Premier lien disponible
    link = element.find("atom:link", ns) or element.find("link")
    if link is not None:
        return link.get("href", "") or (link.text or "").strip()

    return ""


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse une date RSS/Atom."""
    if not date_str:
        return None

    # Formats courants
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",      # RFC 822 (RSS)
        "%a, %d %b %Y %H:%M:%S %Z",      # RFC 822 variante
        "%Y-%m-%dT%H:%M:%S%z",            # ISO 8601 (Atom)
        "%Y-%m-%dT%H:%M:%SZ",             # ISO 8601 UTC
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]

    # Nettoyer la chaîne
    date_str = date_str.strip()
    # Remplacer les timezones textuelles
    date_str = re.sub(r'\s+GMT$', ' +0000', date_str)
    date_str = re.sub(r'\s+UTC$', ' +0000', date_str)

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Dernière tentative : extraire juste la date
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    return None


def _clean_html(text: str) -> str:
    """Nettoie le HTML d'une description."""
    if not text:
        return ""

    # Supprimer les balises HTML
    text = re.sub(r'<[^>]+>', ' ', text)
    # Décoder les entités HTML courantes
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    # Supprimer les espaces multiples
    text = re.sub(r'\s+', ' ', text)

    return text.strip()[:500]


def try_rss_urls(urls: List[str], timeout: int = 10) -> tuple:
    """
    Essaie plusieurs URLs RSS et retourne le premier qui fonctionne.

    Returns:
        (items, url_used) ou ([], None) si aucun ne fonctionne
    """
    for url in urls:
        items = fetch_rss(url, timeout)
        if items:
            return items, url

    return [], None
