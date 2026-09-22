"""
hosts.py
--------
Inventaire PyInfra : liste des serveurs cibles pour le deploiement du
service `metrics-collector`.

PyInfra regroupe automatiquement tous les hotes declares dans ce fichier
(quel que soit le nom de la variable Python utilisee) : ici le groupe
`metrics_servers` contient nos 2 cibles, server1 et server2. Comme c'est
le seul groupe du fichier, `pyinfra hosts.py deploy.py` ciblera les deux.

A adapter avant une execution reelle :
    - Remplacer "server1"/"server2" par les vrais noms d'hote ou IP
      (ou par des alias definis dans ~/.ssh/config).
    - Adapter "ssh_user" si besoin.
    - On suppose un acces SSH par cle deja configure (cf. l'enonce,
      section "Notes").

Utilisation :
    pyinfra hosts.py deploy.py
    pyinfra hosts.py deploy.py --dry   # simulation, sans rien appliquer
"""

metrics_servers = [
    ("server1", {"ssh_user": "ubuntu"}),
    ("server2", {"ssh_user": "ubuntu"}),
]

