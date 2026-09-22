#!/usr/bin/env python3
"""
send_metrics.py
---------------
Genere 10 lignes de metriques "job" aleatoires et les insere dans
ClickHouse (table `job_metrics`) via l'interface HTTP (port 8123),
au format TabSeparated.

Prerequis :
    - ClickHouse joignable en HTTP, par ex. via :
        kubectl port-forward svc/clickhouse-client 8123:8123
    - La table `job_metrics` existe deja (creee automatiquement au 1er
      demarrage du pod, voir configmap.yaml -> cle "init-db.sql").

Utilisation :
    uv run python send_metrics.py
    CLICKHOUSE_URL=http://localhost:8123 uv run python send_metrics.py
"""

import logging
import os
import random
import sys
import time
from datetime import datetime, timedelta

import requests

CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_URL", "http://localhost:8123")
TABLE = "job_metrics"
NB_LIGNES = 10
JOB_NAMES = ["etl_orders", "etl_customers", "backup_daily", "report_weekly", "sync_inventory"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [send-metrics] %(levelname)s: %(message)s",
)
logger = logging.getLogger("send-metrics")


def attendre_clickhouse(url: str, tentatives: int = 10, delai_sec: float = 2.0) -> None:
    """Attend que ClickHouse reponde sur /ping avant d'inserer des donnees.

    Utile juste apres un deploiement k8s : le pod peut mettre quelques
    secondes a devenir Ready (critere "Ops" : robustesse).
    """
    for tentative in range(1, tentatives + 1):
        try:
            r = requests.get(f"{url}/ping", timeout=3)
            if r.ok:
                logger.info("ClickHouse est pret (tentative %d/%d).", tentative, tentatives)
                return
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "ClickHouse pas encore joignable (%s) - tentative %d/%d", exc, tentative, tentatives
            )
        time.sleep(delai_sec)
    raise RuntimeError(f"ClickHouse injoignable sur {url} apres {tentatives} tentatives.")


def generer_lignes(n: int) -> str:
    """Construit le corps TabSeparated attendu par ClickHouse.

    Colonnes, dans l'ordre de la table : job_id, timestamp, duration_sec, success
    """
    lignes = []
    maintenant = datetime.now()
    for _ in range(n):
        job_id = random.choice(JOB_NAMES)
        ts = maintenant - timedelta(minutes=random.randint(0, 24 * 60))
        duration_sec = random.randint(1, 600)
        success = 1 if random.random() > 0.15 else 0  # ~85% de succes, pour rester realiste
        lignes.append(f"{job_id}\t{ts.strftime('%Y-%m-%d %H:%M:%S')}\t{duration_sec}\t{success}")
    return "\n".join(lignes) + "\n"


def inserer_donnees(url: str, payload: str) -> None:
    query = f"INSERT INTO {TABLE} (job_id, timestamp, duration_sec, success) FORMAT TabSeparated"
    response = requests.post(url, params={"query": query}, data=payload.encode("utf-8"), timeout=10)
    response.raise_for_status()  # leve une exception si ClickHouse renvoie une erreur HTTP


def compter_lignes(url: str) -> int:
    """Petite requete de controle, pour verifier que l'insertion a bien fonctionne."""
    response = requests.post(
        url, params={"query": f"SELECT count(*) FROM {TABLE} FORMAT TabSeparated"}, timeout=10
    )
    response.raise_for_status()
    return int(response.text.strip())


def main() -> int:
    logger.info("Cible ClickHouse : %s", CLICKHOUSE_URL)
    try:
        attendre_clickhouse(CLICKHOUSE_URL)

        payload = generer_lignes(NB_LIGNES)
        logger.info("Lignes generees :\n%s", payload)

        inserer_donnees(CLICKHOUSE_URL, payload)
        logger.info("Insertion envoyee avec succes.")

        total = compter_lignes(CLICKHOUSE_URL)
        logger.info("La table '%s' contient maintenant %d ligne(s) au total.", TABLE, total)
        return 0

    except requests.exceptions.RequestException as exc:
        logger.error("Erreur reseau/HTTP en parlant a ClickHouse : %s", exc)
        return 1
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())

