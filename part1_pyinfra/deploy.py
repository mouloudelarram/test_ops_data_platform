"""
deploy.py
---------
Deploiement idempotent du service `metrics-collector` sur les hotes
definis dans hosts.py, a l'aide de PyInfra.

Etapes realisees sur chaque hote :
    1. Creation d'un utilisateur systeme dedie "metrics" (principe de
       moindre privilege : le service ne tourne pas en root).
    2. Creation du repertoire d'installation /opt/metrics-collector.
    3. Copie de metrics_collector.py et du fichier d'unite systemd.
    4. `systemctl daemon-reload` (seulement si l'unite a change),
       activation au boot, et redemarrage (seulement si le code ou
       l'unite ont reellement change sur le serveur cible).

Le point 4 est important : c'est ce qui rend le deploiement VRAIMENT
idempotent. Relancer ce script quand rien n'a change ne redemarre pas
le service inutilement (pas de coupure de service pour rien).

Execution (depuis le dossier part1_pyinfra/) :
    pyinfra hosts.py deploy.py
    pyinfra hosts.py deploy.py --dry     # previsualiser sans rien appliquer
"""

from pyinfra.operations import files, server, systemd

APP_DIR = "/opt/metrics-collector"
SERVICE_USER = "metrics"
SERVICE_NAME = "metrics-collector"

# 1) Utilisateur systeme dedie (pas de shell de connexion, pas de home requis)
server.user(
    name="Creer l'utilisateur systeme 'metrics'",
    user=SERVICE_USER,
    present=True,
    system=True,
    shell="/usr/sbin/nologin",
    _sudo=True,
)

# 2) Repertoire d'installation, appartenant a l'utilisateur du service
files.directory(
    name=f"Creer le repertoire {APP_DIR}",
    path=APP_DIR,
    present=True,
    user=SERVICE_USER,
    group=SERVICE_USER,
    mode="755",
    _sudo=True,
)

# 3a) Copie du script Python de collecte
script = files.put(
    name="Deployer metrics_collector.py",
    src="metrics_collector.py",
    dest=f"{APP_DIR}/metrics_collector.py",
    user=SERVICE_USER,
    group=SERVICE_USER,
    mode="755",
    _sudo=True,
)

# 3b) Copie du fichier d'unite systemd
unit = files.put(
    name="Deployer l'unite systemd metrics-collector.service",
    src="metrics-collector.service",
    dest=f"/etc/systemd/system/{SERVICE_NAME}.service",
    user="root",
    group="root",
    mode="644",
    _sudo=True,
)

# 4) On ne recharge systemd / redemarre le service QUE si le script ou
#    l'unite ont reellement change sur la cible (script.changed / unit.changed
#    sont calcules par PyInfra a partir de l'etat reel du serveur).
systemd.service(
    name="Activer (et redemarrer si besoin) metrics-collector",
    service=SERVICE_NAME,
    running=True,
    enabled=True,
    restarted=script.changed or unit.changed,
    daemon_reload=unit.changed,
    _sudo=True,
)

