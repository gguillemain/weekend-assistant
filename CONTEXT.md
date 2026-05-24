# Weekend Assistant - Contexte de reprise

> Assistant personnel de loisirs pour un couple d'enseignants alsaciens (Guebwiller, Haut-Rhin).
> Génère des suggestions de week-end basées sur la météo, les films, événements, randonnées, concerts et expositions.

## 1. Architecture du projet

```
weekend_assistant/
├── app.py                    # Flask app + routes /, /suggest, /cache-stats, /cache-clear
├── config.py                 # Configuration centralisée (clés API, préférences, distances)
├── requirements.txt          # Dépendances Python
├── .env                      # Variables d'environnement (NON VERSIONNÉ)
├── .gitignore
├── CONTEXT.md                # Ce fichier
│
├── engine/
│   ├── __init__.py
│   ├── calendar_engine.py    # Détection périodes : weekends, ponts, vacances
│   ├── suggest.py            # Orchestration collectors + appel Claude API
│   ├── email_sender.py       # Envoi email hebdomadaire SMTP
│   ├── database.py           # Init SQLite preferences.db
│   ├── profile.py            # Gestion profil, feedback, activités
│   └── cache.py              # Cache SQLite avec TTL par collector
│
├── collectors/
│   ├── __init__.py
│   ├── weather.py            # OpenWeatherMap API (cache 3h)
│   ├── cinema.py             # Scraping Allocine + RSS Télérama/Cahiers (cache 6h)
│   ├── events.py             # Scraping JDS, Strasbourg, Visit Alsace (cache 6h)
│   ├── hiking.py             # Scraping Visorando (cache 24h)
│   ├── travel.py             # Destinations city break / Eurotrip
│   ├── concerts.py           # Ticketmaster API FR/CH/DE, 180km (cache 6h)
│   ├── exhibitions.py        # Scraping fondations/musées, 6 sources (cache 12h)
│   ├── discovery.py          # Bons plans : DNA RSS, Tourisme Alsace, Freiburg (cache 4h)
│   ├── openagenda.py         # API OpenAgenda (4 agendas Alsace)
│   └── rss_reader.py         # Utilitaire parsing RSS/Atom
│
├── templates/
│   ├── index.html            # Interface web responsive
│   └── email.html            # Template email hebdomadaire
│
└── data/
    ├── __init__.py
    ├── database.py           # Module SQLite (legacy)
    ├── activity.db           # Base SQLite feedback (legacy)
    └── preferences.db        # Base SQLite profil/activités/feedback/cache
```

## 2. État des composants

### Fonctionnels (✓)

| Composant | Description | Notes |
|-----------|-------------|-------|
| `calendar_engine.py` | Détecte weekends, ponts (Ascension, 14 juillet...), vacances Zone B | Calendrier 2024-2026 intégré |
| `weather.py` | Prévisions OpenWeatherMap 5 jours | `suitable_outdoor` calculé (temp, pluie), cache 3h |
| `cinema.py` | 3 cinémas : Le Florival, Bel-Air, Le Palace | RSS Télérama strict (★★★★+), cache 6h |
| `events.py` | JDS Alsace, Strasbourg.eu, Visit Alsace | RSS + fallback scraping, cache 6h |
| `hiking.py` | Visorando Haut-Rhin | Filtrage dénivelé max 300m, cache 24h |
| `concerts.py` | Ticketmaster API (FR/CH/DE) | Rayon 180km, déduplication, cache 6h |
| `exhibitions.py` | 6 sources : Beyeler, Schneider, Fernet-Branca, Würth, Strasbourg, Kunstmuseum | profile_match, cache 12h |
| `discovery.py` | DNA RSS (4 feeds), Tourisme Alsace, OpenAgenda, Freiburg | surprise_score, cache 4h |
| `openagenda.py` | API OpenAgenda | 4 agendas : Haut-Rhin, Alsace, Mulhouse, Colmar |
| `cache.py` | Cache SQLite avec TTL | HIT x2600 plus rapide (44s → 17ms) |
| `suggest.py` | Génération suggestions via Claude API | JSON structuré, tous collectors intégrés |
| `profile.py` | Profil utilisateur, feedback, journal | Films/concerts/expos vus, streak_home |
| `index.html` | Interface magazine-style | Responsive, badges colorés, boutons feedback |

### Partiellement fonctionnel (⚠)

| Composant | État | Problème |
|-----------|------|----------|
| Télérama RSS | ⚠ | RSS souvent sans notations explicites → 0 picks |
| Cahiers du Cinéma | ⚠ | Pas de RSS public → scraping fallback |
| JDS/Strasbourg scraping | ⚠ | Structure HTML variable → souvent 0 résultats |
| Freiburg RSS | ⚠ | URLs à vérifier (freiburg.de, badische-zeitung.de) |

### Non implémenté (○)

- Notes Visorando (non visibles dans les cartes)
- Tests unitaires collectors
- OpenAgenda clé API (lecture seule sans clé)

## 3. Système de cache

### TTL par collector

| Collector | TTL | Justification |
|-----------|-----|---------------|
| weather | 3h | Prévisions changent fréquemment |
| cinema | 6h | Séances stables dans la journée |
| events | 6h | Événements stables |
| concerts | 6h | Billetterie stable |
| discovery | 4h | Actualités plus fraîches |
| exhibitions | 12h | Expositions changent peu |
| hiking | 24h | Sentiers très stables |

### Performance mesurée

```
1er appel (CACHE MISS) : 44.5s
2ème appel (CACHE HIT) : 0.017s
Gain : x2600
```

### Routes API

```bash
# Statistiques du cache
curl http://127.0.0.1:5000/cache-stats

# Vider tout le cache
curl -X DELETE http://127.0.0.1:5000/cache-clear

# Vider uniquement les entrées expirées
curl -X DELETE http://127.0.0.1:5000/cache-clear?mode=expired
```

## 4. Sources par collector

### discovery.py (7 sources)

| # | Source | Type | Région |
|---|--------|------|--------|
| 1 | DNA Culture-Loisirs | RSS | Alsace |
| 2 | DNA Insolite | RSS | Alsace |
| 3 | DNA Tourisme & Patrimoine | RSS | Alsace |
| 4 | DNA Gastronomie | RSS | Alsace |
| 5 | Tourisme Alsace | RSS/scraping | Alsace |
| 6 | OpenAgenda | API | Alsace (4 agendas) |
| 7 | Freiburg | RSS | Allemagne |

### exhibitions.py (6 sources)

| Source | Ville | Distance |
|--------|-------|----------|
| Fondation Beyeler | Riehen | 40km |
| Fondation François Schneider | Wattwiller | 10km |
| Fondation Fernet-Branca | Saint-Louis | 38km |
| Musée Würth | Erstein | 58km |
| Musées de Strasbourg | Strasbourg | 100km |
| Kunstmuseum Basel | Bâle | 45km |

## 5. Problèmes connus et contournements

### Télérama false positives
- **Problème** : RSS contenait des articles sans notation
- **Solution** : `_has_positive_rating()` exige ★★★★ explicite ou "coup de cœur"

### Films familiaux dans le top
- **Problème** : Mario, Disney apparaissaient en top
- **Solution** : `_is_family_film()` détecte via titre + genres (pas le texte complet)

### Visorando structure HTML
- **Problème** : Sélecteurs CSS initiaux ne matchaient pas
- **Solution** : `_parse_visorando_card()` utilise `a.card--link[href*='/randonnee-']`

### JSON parsing Claude
- **Problème** : Parfois backticks markdown autour du JSON
- **Solution** : Nettoyage `lstrip("```json")` + fallback texte brut

### Cache et profile_match
- **Problème** : Profile change mais cache reste
- **Solution** : Recalcul profile_match/weather_score au cache HIT

## 6. Prochaines étapes

### Phase 1-5 - Complétées ✓
- [x] Parsing JSON suggestions
- [x] Feedback 👍/👎 fonctionnel
- [x] Scheduler email mercredi
- [x] Mode vacances + suggestions voyage
- [x] Profil utilisateur + historique
- [x] Concerts Ticketmaster
- [x] Expositions (6 sources)
- [x] Cache SQLite (x2600 plus rapide)
- [x] Sources Discovery + OpenAgenda
- [x] Sources allemandes (Freiburg)

### Phase 6 - Améliorations
- [ ] Visorando : notes, photos, GPX
- [ ] Tests unitaires collectors
- [ ] OpenAgenda avec clé API (plus d'agendas)

### Phase 7 - Déploiement
- [ ] VPS OVH (ou autre)
- [ ] Gunicorn + Nginx
- [ ] HTTPS Let's Encrypt
- [ ] Cron job hebdomadaire

## 7. Variables d'environnement

Créer `.env` à la racine :

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENWEATHER_API_KEY=...
FLASK_SECRET_KEY=...
TICKETMASTER_API_KEY=...  # developer.ticketmaster.com

# Configuration SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre.email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx  # App password Gmail
EMAIL_FROM=votre.email@gmail.com
EMAIL_TO=destinataire1@email.com,destinataire2@email.com
```

## 8. Commandes utiles

```bash
# Activer l'environnement
cd /Users/gregmacbook/Documents/Projets/weekend_assistant
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur
python app.py

# Accéder à l'interface
open http://127.0.0.1:5001

# Endpoint debug JSON
curl http://127.0.0.1:5001/suggest | jq

# Statistiques cache
curl http://127.0.0.1:5001/cache-stats | jq

# Vider le cache (force refresh)
curl -X DELETE http://127.0.0.1:5001/cache-clear

# Tester l'envoi d'email
open http://127.0.0.1:5001/test-email
```

## 9. Distances (config.py)

```python
CITY_DISTANCES = {
    # Alsace
    "Guebwiller": 0, "Wattwiller": 10, "Wittelsheim": 12,
    "Mulhouse": 25, "Colmar": 25, "Saint-Louis": 38, "Erstein": 58,
    "Strasbourg": 100,
    # Suisse
    "Bâle": 45, "Basel": 45, "Riehen": 40,
    # Allemagne - Bade-Wurtemberg
    "Freiburg": 50, "Breisach": 35, "Emmendingen": 55,
    "Offenburg": 75, "Lahr": 65, "Kehl": 90,
    "Baden-Baden": 100, "Lörrach": 50, "Weil am Rhein": 45,
    "Bad Krozingen": 45,
    # France - autres
    "Belfort": 55, "Besançon": 120, "Nancy": 150
}
```

## 10. Profil utilisateur

```python
# Musique (pour concerts)
music_artists: ["The Cure", "Pulp", "Fontaines D.C.", "Bertrand Belin"]
music_genres: ["new wave", "post-punk", "jazz", "indie rock"]
music_venues: ["La Laiterie", "Kaserne Basel", "Parc Expo Mulhouse"]

# Expositions
expo_artists: ["Soulages", "Banksy", "surréalistes"]
expo_style: "non-mainstream, contemporain, subversif"
expo_fondations: [
    "Fondation Beyeler Riehen/Bâle",
    "Fondation Schneider Wattwiller",
    "Espace Fernet-Branca Saint-Louis",
    "Musée Würth Erstein"
]
```

**profile_match** (0-1) :
- +0.5 artiste favori
- +0.3 fondation favorite
- +0.2 style correspondant

## 11. Palette couleurs (CSS)

| Couleur | Hex | Usage |
|---------|-----|-------|
| Blanc cassé | #FAFAF8 | Background |
| Vert sauge | #7C9A7E | Accent principal, badges "Spontané" |
| Anthracite | #2C2C2C | Texte |
| Ambre | #E8A838 | Badges "À réserver", Télérama |
| Rouge | #C0392B | Badges "À planifier" |

---

*Dernière mise à jour : 24/05/2026*
*Commits : ba235c2 (MVP) → 15878cd (cache SQLite) → 4220b28 (Freiburg)*
