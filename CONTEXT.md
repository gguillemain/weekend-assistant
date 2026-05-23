# Weekend Assistant - Contexte de reprise

> Assistant personnel de loisirs pour un couple d'enseignants alsaciens (Guebwiller, Haut-Rhin).
> Génère des suggestions de week-end basées sur la météo, les films, événements et randonnées.

## 1. Architecture du projet

```
weekend_assistant/
├── app.py                    # Flask app + routes / + /suggest
├── config.py                 # Configuration centralisée (clés API, préférences)
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
│   └── profile.py            # Gestion profil, feedback, activités
│
├── collectors/
│   ├── __init__.py
│   ├── weather.py            # OpenWeatherMap API
│   ├── cinema.py             # Scraping Allocine + RSS Télérama/Cahiers
│   ├── events.py             # Scraping JDS, Strasbourg, Visit Alsace
│   ├── hiking.py             # Scraping Visorando
│   ├── travel.py             # Destinations city break / Eurotrip
│   ├── concerts.py           # Ticketmaster API + RSS salles locales
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
    └── preferences.db        # Base SQLite profil/activités/feedback
```

## 2. État des composants

### Fonctionnels (✓)

| Composant | Description | Notes |
|-----------|-------------|-------|
| `calendar_engine.py` | Détecte weekends, ponts (Ascension, 14 juillet...), vacances Zone B | Calendrier 2024-2026 intégré |
| `weather.py` | Prévisions OpenWeatherMap 5 jours | `suitable_outdoor` calculé (temp, pluie) |
| `cinema.py` | 3 cinémas : Le Florival, Bel-Air (Mulhouse), Le Palace (Colmar) | RSS Télérama avec matching strict (★★★★+) |
| `events.py` | JDS Alsace, Strasbourg.eu, Visit Alsace | Architecture RSS + fallback scraping |
| `hiking.py` | Visorando Haut-Rhin | Filtrage dénivelé max 300m, distance max 80km |
| `suggest.py` | Génération suggestions via Claude API | Sortie JSON structurée |
| `index.html` | Interface magazine-style | Responsive, badges colorés, boutons feedback |

### Partiellement fonctionnel (⚠)

| Composant | État | Problème |
|-----------|------|----------|
| Télérama RSS | ⚠ | RSS souvent sans notations explicites → 0 picks |
| Cahiers du Cinéma | ⚠ | Pas de RSS public → scraping fallback |
| JDS/Strasbourg scraping | ⚠ | Structure HTML variable → souvent 0 résultats |

### Non implémenté (○)

- Feedback 👍/👎 (HTML présent, pas de backend)
- SQLite activity log
- Scheduler email mercredi
- Mode vacances (suggestions voyage)
- Notes Visorando (non visibles dans les cartes)

## 3. Problèmes connus et contournements

### Télérama false positives
- **Problème** : RSS contenait des articles sans notation
- **Solution** : `_has_positive_rating()` exige ★★★★ explicite ou "coup de cœur"

### Films familiaux dans le top
- **Problème** : Mario, Disney apparaissaient en top
- **Solution** : `_is_family_film()` détecte via titre + genres (pas le texte complet)

### Cinéma L'Entrepôt 404
- **Problème** : Code P0175 inexistant sur Allocine
- **Solution** : Remplacé par Bel-Air (P0663), vrai cinéma art & essai Mulhouse

### Visorando structure HTML
- **Problème** : Sélecteurs CSS initiaux ne matchaient pas
- **Solution** : `_parse_visorando_card()` utilise `a.card--link[href*='/randonnee-']`

### JSON parsing Claude
- **Problème** : Parfois backticks markdown autour du JSON
- **Solution** : Nettoyage `lstrip("```json")` + fallback texte brut

## 4. Prochaines étapes

### Phase 1 - Consolidation
- [x] Parsing JSON suggestions
- [x] Cartes HTML avec badges colorés
- [x] Feedback 👍/👎 fonctionnel (POST /feedback)
- [x] SQLite activity log (`data/activity.db`)

### Phase 2 - Automatisation
- [x] Scheduler email mercredi (APScheduler)
- [x] Template email HTML
- [x] Configuration SMTP dans .env

### Phase 3 - Mode vacances
- [x] Détection `period.mode == "vacances"`
- [x] Suggestions voyage (Eurotrip, city break)
- [ ] Intégration booking/train (optionnel, futur)

### Phase 4 - Améliorations
- [x] Journal d'activité enrichi (films, concerts, expos vus)
- [x] Widget formulaire progressif
- [x] Historique injecté dans prompt Claude
- [ ] Visorando : notes, photos, GPX
- [ ] Cache Redis/fichier pour réduire scraping
- [ ] Tests unitaires collectors

### Phase 5 - Déploiement
- [ ] VPS OVH (ou autre)
- [ ] Gunicorn + Nginx
- [ ] HTTPS Let's Encrypt
- [ ] Cron job hebdomadaire

## 5. Variables d'environnement

Créer `.env` à la racine :

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENWEATHER_API_KEY=...
FLASK_SECRET_KEY=...
TICKETMASTER_API_KEY=...  # developer.ticketmaster.com

# Configuration SMTP (Phase 2)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre.email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx  # App password Gmail
EMAIL_FROM=votre.email@gmail.com
EMAIL_TO=destinataire1@email.com,destinataire2@email.com
```

## 6. Commandes utiles

```bash
# Activer l'environnement
cd /Users/gregmacbook/Documents/Projets/weekend_assistant
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur (avec tests au démarrage)
python app.py

# Accéder à l'interface
open http://127.0.0.1:5001

# Endpoint debug JSON
curl http://127.0.0.1:5001/suggest | jq

# Tester l'envoi d'email
open http://127.0.0.1:5001/test-email

# Tester un collector isolément
python -c "from collectors import weather; print(weather.get_weather_forecast({'start': __import__('datetime').date.today(), 'end': __import__('datetime').date.today(), 'label': 'Test'}))"
```

## 7. Dépendances (requirements.txt)

```
flask
requests
beautifulsoup4
lxml
python-dotenv
anthropic
```

## 8. Palette couleurs (CSS)

| Couleur | Hex | Usage |
|---------|-----|-------|
| Blanc cassé | #FAFAF8 | Background |
| Vert sauge | #7C9A7E | Accent principal, badges "Spontané" |
| Anthracite | #2C2C2C | Texte |
| Ambre | #E8A838 | Badges "À réserver", Télérama |
| Rouge | #C0392B | Badges "À planifier" |

---

*Dernière mise à jour : 23/05/2026*
*Commit initial : ba235c2 (feat: MVP weekend_assistant)*
