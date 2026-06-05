# Weekend Assistant - Contexte de développement

## Vue d'ensemble

Application Flask de suggestions d'activités pour le week-end (région Alsace/Bâle). Collecte des données de plusieurs sources et propose des recommandations personnalisées avec un système de combinaisons d'activités.

## Architecture

```
weekend_assistant/
├── app.py                 # Serveur Flask (port 5001 local, 5000 Docker)
├── config.py              # Configuration (clés API, paramètres)
├── collectors/            # Modules de collecte de données
│   ├── cinema.py          # Films (Télérama RSS, Cahiers du Cinéma)
│   ├── concerts.py        # Concerts (Ticketmaster API)
│   ├── exhibitions.py     # Expositions (scraping musées) + urgency_score
│   ├── events.py          # Événements locaux (JDS, Strasbourg.eu)
│   ├── hiking.py          # Randonnées (Visorando scraping)
│   ├── cycling.py         # Vélo VAE (alsaceavelo.fr scraping)
│   ├── restaurants.py     # Restaurants (Foursquare API)
│   ├── discovery.py       # Découvertes diverses
│   ├── weather.py         # Météo (API OpenWeatherMap)
│   └── travel_flights.py  # Vols BSL (Ryanair/EasyJet + fallback)
├── engine/
│   ├── database.py        # SQLite, schéma, migrations
│   ├── profile.py         # Profil, historique, projets, recommandations
│   ├── suggest.py         # Logique suggestions + build_combos()
│   ├── cache.py           # Cache pour éviter re-scraping
│   ├── calendar_engine.py # Calcul périodes (week-ends, vacances, ponts)
│   └── travel_engine.py   # Suggestions voyages
├── templates/
│   └── index.html         # Frontend (layout 2 colonnes, vanilla JS)
├── data/
│   └── preferences.db     # Base SQLite
├── Dockerfile
└── docker-compose.weekend.yml
```

## Layout Frontend (2 colonnes)

```
┌─────────────────────────────────────────────────────┐
│  HEADER : Weekend Assistant · Période · Météo      │
└─────────────────────────────────────────────────────┘
┌───────────────────────────────┬─────────────────────┐
│  COL-MAIN (flex: 1)           │  COL-SIDEBAR (240px)│
│                               │                     │
│  - Suggestions Claude         │  - Mini calendrier  │
│  - Films Florival (compact)   │  - Prochaines vacs  │
│  - Journal d'activité         │  - Vols BSL         │
│  - Recommandations entourage  │  - Projets (top 4)  │
│  - Projets de vie             │                     │
│  - Mémoires "il y a un an"    │                     │
└───────────────────────────────┴─────────────────────┘
```

## Endpoints API

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/` | GET | Page principale |
| `/suggestions` | GET | API JSON suggestions |
| `/profile` | GET | Profil (`?mode=full` pour historique) |
| `/activity` | POST | Enregistrer activité |
| `/feedback` | POST | Feedback (pouce haut/bas) |
| `/flights` | GET | Vols BSL dynamiques (Ryanair/EasyJet) |
| `/projects` | GET/POST | Liste/Ajout projets de vie |
| `/projects/<id>` | DELETE | Supprimer projet |
| `/projects/<id>/done` | POST | Marquer projet accompli |
| `/projects/suggestions` | GET | Suggestions projets via Claude |
| `/recommendations` | GET/POST | Liste/Ajout recommandations |
| `/recommendations/<id>/done` | POST | Marquer recommandation faite |
| `/memories` | GET | Activités "il y a un an" |
| `/cache-stats` | GET | Stats cache |
| `/cache-clear` | POST | Vider cache |

## Fonctionnalités clés

### 1. Combinaisons d'activités (build_combos)

`engine/suggest.py` construit automatiquement des journées complètes :

| Type | Exemple |
|------|---------|
| `rando_midi` | 🥾🍽️ Sentier des Roches + Auberge du Lac |
| `velo_winstub` | 🚴🍺 Vignoble Rouffach + Winstub |
| `cinema_ville` | 🎬🚶 Film au Florival + balade Guebwiller |
| `expo_gastro` | 🖼️🍽️ Beyeler + Restaurant bâlois |
| `escapade_bale` | 🏛️🇨🇭 Journée Bâle complète |

Badge "Journée complète" affiché sur ces suggestions.

### 2. Projets de vie

Table `life_projects` avec :
- Titre, catégorie (voyage/culture/sport/gastronomie)
- Priorité : 🔥 haute (3), 💛 envie (2), ⭐ rêve (1)
- Mots-clés pour matching automatique avec suggestions

### 3. Recommandations entourage

Table `recommendations` : suggestions de proches (resto, destination, expo...).
Intégrées dans le prompt Claude si pertinentes.

### 4. Urgency Score

Pour expos/concerts avec date de fin proche :
- < 7 jours : score 1.0, "Dernier week-end !"
- < 14 jours : score 0.9, "Plus que X jours"
- Badge `⚠️` sur les cards

### 5. Vols BSL dynamiques

Route `/flights` :
1. Tente APIs Ryanair/EasyJet
2. Fallback données réalistes si APIs indisponibles
3. Mix compagnies : Ryanair, EasyJet, Wizzair, Vueling
4. Cache 24h

### 6. Mini calendrier sidebar

Affiche le mois en cours avec :
- Jour actuel entouré
- Week-ends en vert clair
- Vacances en vert foncé

## Base de données

SQLite dans `data/preferences.db` :

| Table | Description |
|-------|-------------|
| `user_profile` | Clés/valeurs préférences |
| `activity_log` | Historique (films, concerts, expos, randos, vélo, restos) |
| `suggestion_feedback` | Feedback utilisateur |
| `recommendations` | Recommandations de l'entourage |
| `life_projects` | Projets de vie |

## Déploiement VPS

```bash
ssh mathebuchapp@<IP_VPS>
cd ~/weekend-assistant
git pull origin main
docker-compose -f docker-compose.weekend.yml build --no-cache
docker-compose -f docker-compose.weekend.yml up -d
docker logs weekend-assistant --tail 100 -f
```

### Configuration Nginx

Préfixe `/weekend` :
```nginx
location /weekend {
    rewrite ^/weekend(/.*)$ $1 break;
    proxy_pass http://127.0.0.1:5001;
}
```

## Clés API (.env)

```
OPENWEATHERMAP_API_KEY=...
TICKETMASTER_API_KEY=...
FOURSQUARE_API_KEY=...
ANTHROPIC_API_KEY=...
```

## Points d'attention

1. **Chemins relatifs** : Utiliser `./` pour les fetch API
2. **Cache** : Les données sont cachées (météo 3h, vols 24h)
3. **Timeouts** : Vols chargés en async pour éviter 504
4. **Mobile** : Sidebar passe au-dessus sur < 700px

## Développement local

```bash
pip install -r requirements.txt
python app.py  # Port 5001
```
