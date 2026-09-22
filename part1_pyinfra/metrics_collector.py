#!/usr/bin/env python3
"""
metrics_collector.py
---------------------
Service HTTP minimal de "health check" pour la plateforme data.

Pourquoi `http.server` (bibliotheque standard) plutot que Flask ?
    - Zero dependance externe a installer sur server1/server2 : il suffit
      d'avoir un Python 3, ce qui simplifie beaucoup le deploiement PyInfra
      (pas de venv/pip a gerer sur les machines cibles, juste 1 fichier).
    - Pour un simple endpoint /health, http.server est amplement suffisant.

Endpoint expose :
    GET /health -> 200 {"status": "ok"}   (JSON)
    (toute autre route -> 404 {"status": "not found"})

Le service ecoute sur 0.0.0.0:8080 (cf. cahier des charges).
"""

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "0.0.0.0"
PORT = 8080

# systemd capture stdout/stderr du process : un simple logging suffit,
# tout sera visible via `journalctl -u metrics-collector -f`.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [metrics-collector] %(levelname)s: %(message)s",
)
logger = logging.getLogger("metrics-collector")


class HealthHandler(BaseHTTPRequestHandler):
    """Traite les requetes HTTP entrantes."""

    def log_message(self, format: str, *args) -> None:
        # On redirige les logs d'acces par defaut (normalement sur stderr)
        # vers notre logger, pour rester coherent dans journalctl.
        logger.info("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"status": "not found"})

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), HealthHandler)
    logger.info("Demarrage de metrics-collector sur %s:%s", HOST, PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Arret demande (Ctrl+C).")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

