"""Chantier sécurité SECU-TUI (décisions provisoires SECU-1 et SECU-2) : ce qu'un volume piégé fait entrer
dans l'environnement des processus de Hermes, mesuré sur le code de Hermes à la version épinglée.

Constat (run Image Hermes 37784838264, tentative 1) : après un redémarrage du conteneur, une session de la
discussion du tableau de bord a reçu terminal, file et code_execution, exactement la valeur de
HERMES_TUI_TOOLSETS écrite dans /opt/data/.env, alors que /etc/hermes/.env l'épingle à vide.

Cause racine, prouvée ici de façon DÉTERMINISTE : ``load_hermes_dotenv`` publie d'abord /opt/data/.env dans
os.environ (override=True, hermes_cli/env_loader.py:433-434), puis .op.env (441-443), et n'applique la
portée gérée qu'ensuite, par une écriture séparée (env_loader.py:473). Entre les deux, os.environ porte la
valeur du volume pour chaque clé épinglée. Le tableau de bord recharge ce fichier en cours de vie, dans un
autre fil (découverte et reconnexions MCP : tools/mcp_tool_config.py:360-371), pendant que le fil qui
construit l'agent d'une session lit HERMES_TUI_TOOLSETS (tui_gateway/server.py:1912). La sonde ci-dessous
remplace la course par un point d'observation fixe : elle lit os.environ au moment exact où la portée gérée
va être appliquée.

Chaque test passe par la chaîne de production (``commande_gardes`` au démarrage, ``commande_verifier_relance``
à la relance d'un service), puis observe un processus NEUF de Hermes. Exigé : aucune valeur du volume pour une
clé épinglée, ni dans la fenêtre, ni par ``reload.env`` (hermes_cli/config.py:2733-2747, servi par /api/ws).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import acp_demarrage as ad
from conftest import TEMOINS, env_processus, executer_python, installer_home_de_test

UID_HERMES = 10000

# Valeurs « piège » : chacune diffère de la valeur épinglée et rouvrirait quelque chose si elle était lue.
PIEGES_PARTICULIERS = {
    "HERMES_TUI_TOOLSETS": "terminal,file,code_execution",
    "HERMES_SAFE_MODE": "1",
    "HERMES_ACCEPT_HOOKS": "1",
    "HERMES_YOLO_MODE": "1",
    "HERMES_BIN": "/opt/data/faux-hermes",
    "HERMES_ALLOW_PRIVATE_URLS": "true",
    "HERMES_DISABLE_LAZY_INSTALLS": "0",
    "HERMES_DASHBOARD_OIDC_ISSUER": "https://intrus.example",
    "HERMES_DASHBOARD_PUBLIC_URL": "https://intrus.example",
    "HTTPS_PROXY": "http://127.0.0.1:9",
    "SSL_CERT_FILE": "/opt/data/ac-intrus.pem",
    "API_SERVER_HOST": "0.0.0.0",
}


def _pieges(valeurs) -> dict:
    """Une valeur piège pour CHAQUE clé du .env géré, sauf les variables que la garde refuse (testées à part)."""
    gere = ad.valeurs_env_gere(valeurs)
    pieges = {cle: PIEGES_PARTICULIERS.get(cle, "acp-piege") for cle in gere
              if cle not in ad.VARIABLES_VOLUME_INTERDITES}
    assert all(pieges[c] != gere[c] for c in pieges)
    return pieges


def _texte_env(pieges: dict) -> str:
    return "API_SERVER_KEY=0123456789abcdef0123456789\nOPENAI_API_KEY=legitime\n" + "".join(
        f"{cle}={valeur}\n" for cle, valeur in pieges.items())


def _volume_piege(chemins, valeurs, ou: str) -> tuple:
    """Managed scope jetable et volume dont le fichier ``ou`` porte une valeur piège pour chaque clé épinglée.
    Rend (HERMES_HOME du processus sondé, pièges)."""
    installer_home_de_test(chemins, valeurs)
    pieges = _pieges(valeurs)
    home = chemins.hermes_home
    if ou == "env":
        (home / ".env").write_text(_texte_env(pieges), encoding="utf-8")
    elif ou == "op_env":
        (home / ".env").write_text("API_SERVER_KEY=0123456789abcdef0123456789\n", encoding="utf-8")
        (home / ".op.env").write_text(_texte_env(pieges), encoding="utf-8")
    else:
        profil = home / "profiles" / "coder"
        profil.mkdir(parents=True)
        (profil / ".env").write_text(_texte_env(pieges), encoding="utf-8")
        home = profil
    for racine, sous, fichiers in os.walk(chemins.hermes_home):
        os.chown(racine, UID_HERMES, UID_HERMES)
        for nom in fichiers:
            os.chown(Path(racine) / nom, UID_HERMES, UID_HERMES)
    return home, pieges


def _chaine(chemins, env_valide, chaine: str) -> None:
    """La chaîne root de production qui précède tout processus de Hermes."""
    if chaine == "demarrage":
        ad.commande_gardes(chemins, env_valide)
    else:
        ad.commande_verifier_relance(chemins)


SONDE_FENETRE = r'''
import json, os
PIEGES = json.loads(%(pieges)r)
from hermes_cli import env_loader
from tui_gateway import server as _tui
vues = set()
outils = []
_appliquer = env_loader._apply_managed_env
def _sonde(*a, **k):
    # Point fixe : os.environ juste AVANT que la portée gérée ne soit appliquée (env_loader.py:473).
    vues.update(c for c, v in PIEGES.items() if os.environ.get(c) == v)
    if not outils:
        try:
            outils.append(_tui._load_enabled_toolsets("tui"))
        except Exception as exc:
            outils.append("erreur : %%s : %%s" %% (type(exc).__name__, exc))
    return _appliquer(*a, **k)
env_loader._apply_managed_env = _sonde
env_loader.load_hermes_dotenv()
resultat = {"vues_dans_la_fenetre": sorted(vues), "outils_dans_la_fenetre": outils[0] if outils else None,
            "apres": {c: os.environ.get(c) for c in PIEGES}}
'''


@pytest.mark.parametrize("chaine", ["demarrage", "relance"])
@pytest.mark.parametrize("ou", ["env", "op_env", "profil"])
def test_aucune_valeur_du_volume_dans_la_fenetre_de_publication(chemins, valeurs, env_valide, chaine, ou):
    home, pieges = _volume_piege(chemins, valeurs, ou)
    _chaine(chemins, env_valide, chaine)
    env = env_processus(chemins, HERMES_HOME=str(home))
    resultat = executer_python(SONDE_FENETRE % {"pieges": json.dumps(pieges)}, env=env)
    print(json.dumps(resultat, ensure_ascii=False, indent=1))
    gere = ad.valeurs_env_gere(valeurs)
    # Contrôle : la portée gérée gagne bien à la fin (sinon la sonde mesurerait autre chose).
    assert resultat["apres"] == {c: gere[c] for c in pieges}
    outils = resultat["outils_dans_la_fenetre"]
    assert isinstance(outils, list), outils
    assert not {"terminal", "file", "code_execution"} & set(outils), (
        f"dans la fenêtre, une session du tableau de bord recevrait {outils}")
    assert resultat["vues_dans_la_fenetre"] == [], (
        "valeurs du volume publiées dans os.environ avant la portée gérée : "
        + ", ".join(resultat["vues_dans_la_fenetre"]))


SONDE_CONCURRENTE = r'''
import os, threading, time
from hermes_cli.env_loader import load_hermes_dotenv
from tui_gateway import server as _tui
arret = threading.Event()
rechargements = [0]
def recharger():
    # Comme _load_mcp_config (tools/mcp_tool_config.py:368-371) dans le fil de découverte MCP.
    while not arret.is_set():
        load_hermes_dotenv()
        rechargements[0] += 1
fil = threading.Thread(target=recharger, daemon=True)
fil.start()
lectures = avec_terminal = 0
fin = time.monotonic() + 4.0
while time.monotonic() < fin:
    choisis = _tui._load_enabled_toolsets("tui")
    lectures += 1
    if choisis is None or "terminal" in choisis:
        avec_terminal += 1
arret.set()
fil.join(10)
resultat = {"lectures": lectures, "avec_terminal": avec_terminal, "rechargements": rechargements[0],
            "final": os.environ.get("HERMES_TUI_TOOLSETS")}
'''


def test_concurrence_reelle_d_un_rechargeur_et_du_fil_d_une_session(chemins, valeurs, env_valide):
    """La course telle qu'elle se produit dans le tableau de bord : un fil recharge le .env (MCP) pendant que
    le fil d'une session résout ses outils par la fonction réelle de Hermes. Fréquence mesurée et affichée."""
    home, _ = _volume_piege(chemins, valeurs, "env")
    _chaine(chemins, env_valide, "relance")
    resultat = executer_python(SONDE_CONCURRENTE, env=env_processus(chemins, HERMES_HOME=str(home)))
    print(json.dumps(resultat, ensure_ascii=False))
    assert resultat["lectures"] > 20 and resultat["rechargements"] > 20, resultat
    assert resultat["avec_terminal"] == 0, (
        f"{resultat['avec_terminal']} résolution(s) sur {resultat['lectures']} ont rendu terminal")


SONDE_RELOAD_ENV = r'''
import json, os
PIEGES = json.loads(%(pieges)r)
from hermes_cli.env_loader import load_hermes_dotenv
from hermes_cli import config
load_hermes_dotenv()
avant = {c: os.environ.get(c) for c in PIEGES}
change = config.reload_env()
resultat = {"avant": avant, "apres": {c: os.environ.get(c) for c in PIEGES}, "changees": change}
'''


def test_reload_env_ne_republie_aucune_valeur_du_volume(chemins, valeurs, env_valide):
    """« reload.env » (tui_gateway/methods_tools.py:251) recopie /opt/data/.env dans os.environ SANS la portée
    gérée, jusqu'au chargement suivant : après la chaîne de relance, il ne doit plus rien y trouver."""
    home, pieges = _volume_piege(chemins, valeurs, "env")
    _chaine(chemins, env_valide, "relance")
    resultat = executer_python(SONDE_RELOAD_ENV % {"pieges": json.dumps(pieges)},
                               env=env_processus(chemins, HERMES_HOME=str(home)))
    print(json.dumps(resultat, ensure_ascii=False, indent=1))
    publiees = sorted(c for c, v in resultat["apres"].items() if v == pieges[c])
    assert publiees == [], f"reload.env republie les valeurs du volume de : {', '.join(publiees)}"
    # Les épingles qui ferment l'exécution et le réseau privé tiennent après reload.env.
    apres = resultat["apres"]
    for cle in ("HERMES_TUI_TOOLSETS", "HERMES_SAFE_MODE", "HERMES_BIN", "HERMES_ACCEPT_HOOKS", "HERMES_YOLO_MODE"):
        assert apres[cle] in ("", None), (cle, apres[cle])
    assert apres["HERMES_ALLOW_PRIVATE_URLS"] == "false"
    assert apres["HERMES_DISABLE_LAZY_INSTALLS"] == "1"


# ------------------------------------------------------------------ .op.env et la portée gérée


@pytest.mark.parametrize("ou", ["racine", "profil"])
def test_hermes_managed_dir_dans_op_env_est_refuse(chemins, valeurs, env_valide, ou):
    """/opt/data/.op.env est chargé AVANT la portée gérée (env_loader.py:441-443) ; HERMES_MANAGED_DIR posée là
    choisirait le .env géré lu (managed_scope.py:52). Refus au démarrage et à la relance, comme pour .env."""
    installer_home_de_test(chemins, valeurs)
    dossier = chemins.hermes_home if ou == "racine" else chemins.hermes_home / "profiles" / "coder"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / ".op.env").write_text(f"HERMES_MANAGED_DIR={chemins.hermes_home / 'faux'}\n", encoding="utf-8")
    attendu = f"{dossier / '.op.env'} définit la variable interdite HERMES_MANAGED_DIR"
    trouvees = ad.variables_interdites_dans_le_volume(chemins)
    assert [(f, n) for f, n, _ in trouvees] == [(dossier / ".op.env", "HERMES_MANAGED_DIR")]
    for refuser in (ad.refuser_variables_du_volume, ad.commande_verifier_relance,
                    lambda c: ad.commande_gardes(c, env_valide)):
        with pytest.raises(ad.Refus) as refus:
            refuser(chemins)
        assert attendu in str(refus.value)


# ------------------------------------------------------------------ sources externes de secrets


def _config_secrets(commande: str) -> str:
    return f"secrets:\n  command:\n    enabled: true\n    command: \"{commande}\"\n"


def test_temoin_hermes_execute_la_commande_de_secrets_du_volume(chemins, valeurs, temoins):
    """Témoin (comportement de Hermes, sans garde) : ``secrets.command`` du config.yaml du volume est lu SANS la
    portée gérée (env_loader.py:620-640) et lancé par ``/bin/sh -c`` au premier chargement de l'environnement de
    CHAQUE processus (env_loader.py:471-472 ; agent/secret_sources/command.py:61-80)."""
    temoin = temoins / "secrets-command"
    installer_home_de_test(chemins, valeurs, config=_config_secrets(f"touch {temoin}"))
    executer_python("from hermes_cli.env_loader import load_hermes_dotenv\nload_hermes_dotenv()\nresultat = 1\n",
                    env=env_processus(chemins))
    assert temoin.exists(), "Hermes n'a pas exécuté secrets.command : le témoin ne prouve plus le vecteur"


@pytest.mark.parametrize("ou", ["racine", "profil"])
def test_une_source_de_secrets_du_volume_est_refusee(chemins, valeurs, env_valide, ou):
    installer_home_de_test(chemins, valeurs)
    dossier = chemins.hermes_home if ou == "racine" else chemins.hermes_home / "profiles" / "coder"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "config.yaml").write_text(_config_secrets(f"touch {TEMOINS}/secrets"), encoding="utf-8")
    attendu = f"{dossier / 'config.yaml'} active la source externe de secrets « command »"
    scope = ad.preparer_scope_geree(chemins, valeurs)
    for refuser in (ad.commande_verifier_relance, lambda c: ad.commande_gardes(c, env_valide),
                    lambda c: ad.preparer_donnees(c, scope, uid=UID_HERMES, gid=UID_HERMES)):
        with pytest.raises(ad.Refus) as refus:
            refuser(chemins)
        assert attendu in str(refus.value)
    # La maintenance la signale aussi.
    assert any("secrets.command" in c for c in ad.inventaire_cles_executables(chemins))
