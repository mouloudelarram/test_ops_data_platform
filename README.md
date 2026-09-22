# Test technique – Ingénieur(e) Data Platform Ops

> 📄 Énoncé original : [`Case Data Ops senior.docx`](./Case%20Data%20Ops%20senior.docx)
> ⏱️ Durée indicative : 1 heure — 🧰 Technologies : Python, uv, systemd, PyInfra, Kubernetes, ClickHouse

Ce dépôt contient le rendu du test technique, en deux parties :

1. **Partie 1 (« Old School »)** : un service de health-check Python, packagé en service `systemd`, déployé de façon automatisée et idempotente sur 2 serveurs avec **PyInfra**.
2. **Partie 2 (« New School »)** : une base **ClickHouse** déployée sur **Kubernetes**, avec un script Python qui y insère des métriques simulées.

> 💡 **Note pour la relecture** : je suis junior sur certains de ces sujets (PyInfra, Kubernetes, ClickHouse), donc ce README détaille aussi le **« pourquoi »** de chaque choix, pas seulement le « quoi ». L'idée est de pouvoir réexpliquer/défendre chaque décision à l'oral.

---

## 📂 Arborescence du rendu

```
test_ops_data_platform/
├── pyproject.toml                  # dépendances Python (gérées avec uv)
├── part1_pyinfra/
│   ├── metrics_collector.py        # le service HTTP /health
│   ├── metrics-collector.service   # l'unité systemd
│   ├── hosts.py                    # inventaire PyInfra (server1, server2)
│   └── deploy.py                   # le déploiement PyInfra (idempotent)
└── part2_k8s_clickhouse/
    ├── clickhouse-deployment.yaml  # StatefulSet ClickHouse (1 instance)
    ├── clickhouse-service.yaml     # Services (headless + client)
    ├── configmap.yaml              # config ClickHouse + script de création de table
    └── send_metrics.py             # génère et insère 10 lignes de métriques
```

---

## 🧱 Partie 1 — PyInfra / systemd

### Ce qui a été fait

- **`metrics_collector.py`** : un serveur HTTP écrit avec `http.server` (bibliothèque standard, donc **zéro dépendance à installer sur les serveurs cibles** — juste besoin de Python 3). Il expose `GET /health` → `200 {"status": "ok"}` sur le port `8080`.
- **`metrics-collector.service`** : une unité systemd qui :
  - démarre au boot (`WantedBy=multi-user.target` + service *enabled*) ;
  - redémarre automatiquement en cas de crash (`Restart=always`) ;
  - envoie ses logs à `journald` (consultables avec `journalctl -u metrics-collector -f`) ;
  - tourne sous un utilisateur dédié `metrics` (pas root → principe de moindre privilège).
- **`hosts.py` / `deploy.py`** : le déploiement PyInfra qui, sur `server1` et `server2` :
  1. crée l'utilisateur système `metrics` ;
  2. crée `/opt/metrics-collector` ;
  3. copie `metrics_collector.py` et le fichier `.service` ;
  4. recharge systemd (`daemon-reload`) et démarre/active le service.

### Pourquoi ces choix ?

- **`http.server` plutôt que Flask** : évite d'avoir à installer un environnement Python (venv, pip, dépendances) sur chaque serveur de prod. Un simple `python3` suffit. C'est plus « ops-friendly ».
- **Idempotence « intelligente »** : dans `deploy.py`, le service n'est redémarré (`restarted=...`) et systemd rechargé (`daemon_reload=...`) **que si le code ou l'unité ont réellement changé** sur le serveur (`script.changed`, `unit.changed`). Ça évite de couper le service à chaque exécution du script si rien n'a changé — c'est ce qu'on entend par « vraie » idempotence, pas juste « ça ne plante pas si on relance ».
- **Utilisateur dédié `metrics`** : bonne pratique de sécurité classique (le service n'a pas besoin des droits root pour écouter sur le port 8080 et répondre à des requêtes HTTP).

### Comment tester

```powershell
# 1. Installer les dépendances (uv crée un .venv automatiquement)
uv sync

# 2. Tester le service localement (sans PyInfra, sans systemd)
uv run python part1_pyinfra/metrics_collector.py
# puis dans un autre terminal :
curl http://localhost:8080/health
# -> {"status": "ok"}

# 3. Déploiement réel sur server1/server2 (adapter hosts.py avant !)
cd part1_pyinfra
uv run pyinfra hosts.py deploy.py --dry   # simulation d'abord
uv run pyinfra hosts.py deploy.py         # déploiement réel

# 4. Vérification côté serveur (en SSH sur server1 par ex.)
systemctl status metrics-collector
journalctl -u metrics-collector -f
curl http://localhost:8080/health
```

> ⚠️ `hosts.py` utilise `server1`/`server2` comme placeholders : remplace-les par les vrais noms/IP de tes machines (ou des alias `~/.ssh/config`), avec un accès SSH par clé déjà en place (cf. énoncé).

---

## ☸️ Partie 2 — Kubernetes / ClickHouse

### Ce qui a été fait

- **`clickhouse-deployment.yaml`** : un **StatefulSet** (1 replica) plutôt qu'un Deployment classique — voir « Pourquoi » ci-dessous. Il monte :
  - un volume persistant (`volumeClaimTemplates`, 2Gi) pour `/var/lib/clickhouse` (les données survivent à un redémarrage du pod) ;
  - la config additionnelle et le script SQL fournis par la ConfigMap ;
  - des probes `readiness`/`liveness` sur l'endpoint `/ping` de ClickHouse.
- **`clickhouse-service.yaml`** : deux Services :
  - `clickhouse` (*headless*) : requis par le StatefulSet pour l'identité réseau du pod ;
  - `clickhouse-client` (ClusterIP) : celui qu'on utilise pour se connecter (via `kubectl port-forward`).
- **`configmap.yaml`** : contient
  - un override de config ClickHouse (niveau de logs) ;
  - le script `init-db.sql` qui crée la table `job_metrics` **automatiquement au premier démarrage** du pod (mécanisme `/docker-entrypoint-initdb.d/` de l'image officielle, comme pour les images Postgres/MySQL).
- **`send_metrics.py`** : génère 10 lignes aléatoires et les insère dans ClickHouse via HTTP (port 8123) au format `TabSeparated`, avec une petite logique de *retry* (attend que ClickHouse soit prêt) et des logs clairs.

### Pourquoi ces choix ?

- **StatefulSet plutôt que Deployment** : ClickHouse est une base de données (« stateful »). Un StatefulSet gère lui-même le cycle de vie du volume associé au pod et lui donne une identité stable (`clickhouse-0`). Un Deployment + PVC partagé fonctionnerait aussi pour 1 seule instance, mais le StatefulSet est le choix « standard » pour ce type de charge de travail, même à 1 replica.
- **Création de la table via ConfigMap (`/docker-entrypoint-initdb.d/`)** plutôt qu'un script à lancer manuellement : c'est automatique, reproductible, et ça ne s'exécute qu'une seule fois (tant que le volume de données n'est pas vide) — donc pas de risque de recréer la table à chaque redémarrage.
- **Deux Services distincts** : c'est un détail « Kubernetes idiomatique » — le service *headless* sert l'infrastructure interne du StatefulSet, le service *client* sert les vrais consommateurs (ici, `send_metrics.py`).
- **Probes sur `/ping`** : endpoint ultra léger fourni nativement par ClickHouse, parfait pour que Kubernetes sache quand le pod est réellement prêt à recevoir du trafic.

### Comment tester (avec Minikube, k3d ou Docker Desktop)

```powershell
# 1. Démarrer un cluster local (exemple avec minikube)
minikube start

# 2. Déployer ClickHouse
kubectl apply -f part2_k8s_clickhouse/configmap.yaml
kubectl apply -f part2_k8s_clickhouse/clickhouse-deployment.yaml
kubectl apply -f part2_k8s_clickhouse/clickhouse-service.yaml

# 3. Attendre que le pod soit prêt
kubectl get pods -w
# -> clickhouse-0   1/1   Running

# 4. Ouvrir un accès local vers ClickHouse (dans un terminal dédié, le laisser tourner)
kubectl port-forward svc/clickhouse-client 8123:8123

# 5. (optionnel) Vérifier que la table a bien été créée
curl "http://localhost:8123/?query=SHOW%20TABLES"

# 6. Générer et insérer les métriques
uv run python part2_k8s_clickhouse/send_metrics.py

# 7. Vérifier les données insérées
curl "http://localhost:8123/?query=SELECT%20*%20FROM%20job_metrics"
```

### Debug rapide

```powershell
kubectl describe pod clickhouse-0        # évènements, erreurs de scheduling/probe
kubectl logs clickhouse-0                # logs du serveur ClickHouse
kubectl logs clickhouse-0 --previous     # logs du conteneur précédent (si crash)
```

---

## 📌 Récapitulatif face aux critères d'évaluation

| Compétence | Ce que ce rendu propose |
|---|---|
| Python | Code sans dépendance inutile, typé, commenté, logs clairs (`logging`) |
| systemd | `Restart=always`, logs via journald, utilisateur dédié, démarrage au boot |
| PyInfra | Idempotence réelle (restart conditionnel), inventaire séparé, lisible |
| Kubernetes | StatefulSet + volume + probes + 2 Services, YAML commenté |
| ClickHouse | Table créée automatiquement, ingestion HTTP vérifiée par un `count(*)` |
| Ops | Logs partout, retry/backoff, commandes de debug documentées ci-dessus |

---

## 🎓 Petit lexique (pour la revue / l'entretien)

- **Idempotent** : on peut exécuter l'action plusieurs fois, le résultat final est le même qu'en l'exécutant une seule fois (pas d'effet de bord cumulatif).
- **systemd unit** : fichier de config qui décrit à Linux comment démarrer/surveiller/redémarrer un programme en tant que service.
- **StatefulSet** : ressource Kubernetes pour les applications avec état (bases de données...), qui donne une identité stable + un volume dédié à chaque instance.
- **ConfigMap** : objet Kubernetes qui stocke de la config (texte) injectable dans un pod, sans la coder en dur dans l'image.
- **Probe (readiness/liveness)** : vérification périodique par Kubernetes qu'un pod répond bien, pour décider s'il doit recevoir du trafic (*readiness*) ou être redémarré (*liveness*).

