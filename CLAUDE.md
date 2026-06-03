# Weekend Assistant - Contexte de développement

## Vue d'ensemble

Application Flask de suggestions d'activités pour le week-end (région Alsace/Bâle). Collecte des données de plusieurs sources (cinéma, concerts, expos, randonnées, restaurants, météo) et propose des recommandations personnalisées.

## Architecture

```
weekend_assistant/
├── app.py                 # Serveur Flask principal (port 5001 local, 5000 Docker)
├── config.py              # Configuration (clés API, paramètres)
├── collectors/            # Modules de collecte de données
│   ├── cinema.py          # Films (Télérama RSS, Cahiers du Cinéma)
│   ├── concerts.py        # Concerts (Ticketmaster API)
│   ├── exhibitions.py     # Expositions (scraping musées)
│   ├── events.py          # Événements locaux (JDS, Strasbourg.eu)
│   ├── hiking.py          # Randonnées (Visorando scraping)
│   ├── restaurants.py     # Restaurants (Foursquare API)
│   ├── discovery.py       # Découvertes diverses
│   └── weather.py         # Météo (API OpenWeatherMap)
├── engine/
│   ├── database.py        # Connexion SQLite, schéma
│   ├── profile.py         # Gestion profil utilisateur, historique
│   ├── cache.py           # Système de cache pour éviter re-scraping
│   └── suggestions.py     # Logique de recommandation
├── templates/
│   └── index.html         # Frontend (HTML/CSS/JS vanilla)
├── data/
│   └── preferences.db     # Base SQLite (profil, historique, feedback)
├── Dockerfile
└── docker-compose.weekend.yml
```

## Endpoints API principaux

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/` | GET | Page principale avec suggestions |
| `/suggestions` | GET | API JSON des suggestions |
| `/profile` | GET | Profil et historique (`?mode=full` pour historique complet) |
| `/activity` | POST | Enregistrer une activité du week-end |
| `/mark-as-done` | POST | Marquer une suggestion comme faite |
| `/feedback` | POST | Envoyer un feedback (pouce haut/bas) |
| `/cache-stats` | GET | Statistiques du cache |
| `/cache-clear` | POST | Vider le cache |

## Déploiement VPS

### Configuration

- **Chemin VPS** : `~/weekend-assistant/`
- **Utilisateur** : `mathebuchapp`
- **Container** : `weekend-assistant`
- **Port interne** : 5000
- **Port exposé** : 127.0.0.1:5001
- **Reverse proxy** : Nginx sur `/weekend`

### Configuration Nginx

L'application est servie sous le préfixe `/weekend` :
```nginx
location /weekend {
    rewrite ^/weekend(/.*)$ $1 break;
    rewrite ^/weekend$ / break;
    proxy_pass http://127.0.0.1:5001;
    # ... headers et timeouts
}
```

**Important** : Les appels fetch frontend utilisent des chemins relatifs (`./profile`, `./suggestions`) pour fonctionner avec ce préfixe.

### Commandes de déploiement

```bash
# Se connecter au VPS
ssh mathebuchapp@<IP_VPS>

# Aller dans le projet
cd ~/weekend-assistant

# Mettre à jour le code
git pull origin main

# Reconstruire et relancer le conteneur
docker-compose -f docker-compose.weekend.yml build --no-cache
docker-compose -f docker-compose.weekend.yml up -d

# Voir les logs
docker logs weekend-assistant --tail 100 -f

# Vérifier l'état
docker ps | grep weekend
```

### Commandes de debug

```bash
# Tester un endpoint depuis le VPS
curl http://127.0.0.1:5001/profile?mode=full | jq

# Voir la base de données
docker exec weekend-assistant ls -la /app/data/

# Redémarrer sans rebuild
docker-compose -f docker-compose.weekend.yml restart

# Logs nginx
sudo tail -f /var/log/nginx/error.log
```

## Base de données

SQLite stockée dans `data/preferences.db` (volume Docker monté).

### Tables principales

- **activity_log** : Historique des activités (films vus, concerts, expos, randos, restaurants)
- **suggestion_feedback** : Feedback utilisateur sur les suggestions
- **user_profile** : Préférences utilisateur

### Déduplication

Les collectors utilisent `get_seen_items_normalized()` pour éviter de re-suggérer des éléments déjà vus :
- Concerts/Expos : 365 jours
- Randonnées/Restaurants : 90 jours
- Discovery : 180 jours

## Points d'attention

1. **Après chaque modification** : Reconstruire l'image Docker sur le VPS
2. **Chemins relatifs** : Utiliser `./` pour les fetch API (commit c040086)
3. **Rate limiting** : Ticketmaster peut renvoyer 429 (Too Many Requests)
4. **Cache** : Les données sont cachées pour éviter le scraping excessif
5. **Healthcheck** : Le conteneur peut apparaître "unhealthy" si `/cache-stats` timeout

## Clés API requises (.env)

```
OPENWEATHERMAP_API_KEY=...
TICKETMASTER_API_KEY=...
FOURSQUARE_API_KEY=...
```

## Développement local

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer en local
python app.py  # Port 5001

# Ou avec Docker
docker-compose -f docker-compose.weekend.yml up --build
```
