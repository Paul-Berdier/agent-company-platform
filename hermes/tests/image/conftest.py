"""Tests exécutés DANS l'image de test (``hermes/tests/Dockerfile``), en root, avec
l'interpréteur de Hermes :

  docker run --rm --entrypoint /opt/hermes/.venv/bin/python -e PYTHONPATH=/opt/acp-tests/site \
      acp-hermes-tests:ci -m pytest -p no:cacheprovider /opt/acp-tests/image

Ils ne tournent nulle part ailleurs : ils importent le code de Hermes à la version
épinglée et les fichiers de l'image (/opt/acp, /opt/hermes/plugins/acp-poste). Chaque test
travaille dans un HERMES_HOME et une managed scope jetables (tmp_path), jamais dans
/opt/data ni /etc/hermes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BIN_ACP = Path("/opt/acp/bin")
GREFFON = Path("/opt/hermes/plugins/acp-poste")
OUTILS = Path("/opt/acp-tests/outils")

if not (BIN_ACP / "acp_demarrage.py").is_file() or not GREFFON.is_dir():
    raise RuntimeError(
        "Ces tests s'exécutent dans l'image de test ACP (hermes/tests/Dockerfile), pas ailleurs.")

for chemin in (BIN_ACP, GREFFON):
    if str(chemin) not in sys.path:
        sys.path.insert(0, str(chemin))

import acp_demarrage as ad  # noqa: E402

ENV_VALIDE = {
    "HERMES_HOME": "/opt/data",
    "HERMES_WEB_DIST": "/opt/hermes/hermes_cli/web_dist",
    "HERMES_DASHBOARD": "1",
    "HERMES_DASHBOARD_HOST": "0.0.0.0",
    "HERMES_DASHBOARD_PORT": "9119",
    "S6_BEHAVIOUR_IF_STAGE2_FAILS": "2",
    "S6_STAGE2_HOOK": "/opt/acp/bin/acp-gardes",
    "HERMES_DASHBOARD_PUBLIC_URL": "https://hermes.acp.test",
    "HERMES_DASHBOARD_OIDC_ISSUER": "https://idp.acp.test:8443",
    "HERMES_DASHBOARD_OIDC_CLIENT_ID": "acp-tableau",
    "PATH": "/usr/bin:/bin",
    "HOSTNAME": "conteneur",
}


@pytest.fixture
def env_valide() -> dict:
    return dict(ENV_VALIDE)


@pytest.fixture
def valeurs() -> "ad.ValeursDeploiement":
    return ad.verifier_environnement(ENV_VALIDE)


@pytest.fixture
def chemins(tmp_path: Path) -> "ad.Chemins":
    """Arborescence jetable : managed scope, HERMES_HOME, état ; modèle, thème et SOUL de l'image.

    Les parents de tmp_path sont rendus traversables (0755) : sans cela, un test « l'uid
    hermes ne peut pas écrire » réussirait pour une mauvaise raison (répertoire parent
    fermé), ce que les contrôles positifs des tests vérifient."""
    for parent in (tmp_path, tmp_path.parent, tmp_path.parent.parent):
        os.chmod(parent, 0o755)
    gere = tmp_path / "etc-hermes"
    gere.mkdir(mode=0o755)
    os.chmod(gere, 0o755)
    home = tmp_path / "opt-data"
    home.mkdir()
    os.chown(home, 10000, 10000)
    return ad.Chemins(
        modele_gere=Path("/opt/acp/gere/config.yaml"),
        dossier_gere=gere,
        hermes_home=home,
        theme_livre=Path("/opt/acp/theme"),
        soul_livre=Path("/opt/acp/persona/SOUL.md"),
        soul_amont=Path("/opt/hermes/docker/SOUL.md"),
        dossier_etat=tmp_path / "run-acp",
    )
