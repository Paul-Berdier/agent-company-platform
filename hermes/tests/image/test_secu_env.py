"""Chantier sécurité SECU-TUI (décisions SECU-1 et SECU-2, D156 et D157 du plan) : ce qu'un volume piégé fait entrer
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


# Clés épinglées que Hermes RETIRE d'os.environ quand le .env du volume ne les porte pas, ce que SECU-1 assure :
# dans la fenêtre de chaque rechargement (_clear_known_keys_missing_from_dotenv, env_loader.py:82-94, liste
# _PROFILE_MANAGED_ENV_KEYS) et par reload_env (hermes_cli/config.py:2743-2746, OPTIONAL_ENV_VARS et
# _EXTRA_ENV_KEYS), jusqu'au chargement suivant. Elles sont alors ABSENTES un instant, au lieu de valoir leur
# épingle ; toute autre clé épinglée qui deviendrait absente fait échouer le test ci-dessous (à analyser).
ABSENCES_ADMISES = {"API_SERVER_HOST", "API_SERVER_PORT", "HERMES_COPILOT_ACP_COMMAND", "HERMES_COPILOT_ACP_ARGS",
                    "COPILOT_CLI_PATH"}

SONDE_ABSENCES = r'''
import json, os
from pathlib import Path
from dotenv import dotenv_values
GERE = {k: (v or "") for k, v in dotenv_values(Path(os.environ["HERMES_MANAGED_DIR"]) / ".env",
                                                 interpolate=False).items()}
from hermes_cli import env_loader, config
def etat():
    return {"absentes": sorted(k for k in GERE if os.environ.get(k) is None),
            "autres": sorted(k for k, v in GERE.items() if os.environ.get(k) not in (None, v))}
def lecteurs():
    # Les lecteurs de Hermes de ces clés, avec leurs valeurs par défaut (gateway/platforms/api_server.py:204-219 ;
    # tools/cronjob_tools.py:102-122 ; hermes_cli/web_server_cron.py:315-370 ; security_audit_startup.py:121-140 ;
    # agent/copilot_acp_client.py:75-80).
    from gateway.platforms.api_server import listen_address
    from tools.cronjob_tools import _api_server_base_url
    from hermes_cli.web_server_cron import _cron_default_profile, _gateway_fire_endpoint
    from hermes_cli.security_audit_startup import _network_listener_without_auth
    from agent.copilot_acp_client import _resolve_args, _resolve_command
    return {"api_server_ecoute": list(listen_address({})),
            "api_server_url_des_outils_cron": _api_server_base_url(),
            "api_server_url_du_tableau_de_bord": _gateway_fire_endpoint(_cron_default_profile(),
                                                                        Path(os.environ["HERMES_HOME"])),
            "audit_api_server": _network_listener_without_auth({"platforms": {"api_server": {"enabled": True}}}),
            "copilot_commande": _resolve_command(), "copilot_arguments": _resolve_args()}
env_loader.load_hermes_dotenv()
reference = {"etat": etat(), "lecteurs": lecteurs()}
fenetre = {}
appliquer = env_loader._apply_managed_env
def sonde(*a, **k):
    # Point fixe d'un RECHARGEMENT en cours de vie (le premier chargement a déjà appliqué la portée gérée).
    if not fenetre:
        fenetre.update(etat=etat(), lecteurs=lecteurs())
    return appliquer(*a, **k)
env_loader._apply_managed_env = sonde
env_loader.load_hermes_dotenv()
env_loader._apply_managed_env = appliquer
config.reload_env()
resultat = {"reference": reference, "fenetre": fenetre, "reload_env": {"etat": etat(), "lecteurs": lecteurs()}}
'''


def test_les_epingles_absentes_un_instant_valent_leur_epingle(chemins, valeurs, env_valide):
    """Effet de bord de SECU-1, mesuré : le volume ne portant plus les clés épinglées, Hermes en retire quelques-
    unes d'os.environ dans la fenêtre d'un rechargement et après « reload.env » (servi par /api/ws). Exigé : aucune
    autre valeur que l'épingle ou l'absence, des absences limitées à ABSENCES_ADMISES, et des lecteurs de Hermes
    qui rendent EXACTEMENT ce qu'ils rendent avec l'épingle (127.0.0.1:8642, programme copilot par défaut)."""
    home, _ = _volume_piege(chemins, valeurs, "env")
    _chaine(chemins, env_valide, "relance")
    resultat = executer_python(SONDE_ABSENCES, env=env_processus(chemins, HERMES_HOME=str(home)))
    print(json.dumps(resultat, ensure_ascii=False, indent=1))
    reference = resultat["reference"]
    assert reference["etat"] == {"absentes": [], "autres": []}, reference["etat"]
    assert reference["lecteurs"]["api_server_ecoute"] == ["127.0.0.1", 8642], reference["lecteurs"]
    for moment in ("fenetre", "reload_env"):
        mesure = resultat[moment]
        assert mesure["etat"]["autres"] == [], (moment, mesure["etat"])
        assert set(mesure["etat"]["absentes"]) <= ABSENCES_ADMISES, (moment, mesure["etat"])
        assert mesure["lecteurs"] == reference["lecteurs"], (moment, mesure["lecteurs"], reference["lecteurs"])
    # Contrôle : les absences mesurées existent bien (sinon le test passerait à vide).
    assert resultat["reload_env"]["etat"]["absentes"], resultat["reload_env"]


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


# ------------------------------------------------------------------ variables d'emplacement et d'exécution (audit)
#
# Audit défensif du 9 octobre 2026, manque 1 : une variable qui choisit un répertoire ou un programme, posée dans
# un .env du volume, est publiée par Hermes (override=True, env_loader.py:433-434) et SUIVIE ensuite :
# get_hermes_home() relit HERMES_HOME dans os.environ à chaque appel (hermes_constants.py:112-119 et 161-170), donc
# tout ce que Hermes lit après vient d'un répertoire qu'aucune garde n'inspecte. Ni refusées, ni épinglées, ni
# retirées jusque-là. Famille attendue, calculée ICI sans la liste d'ACP : les valeurs que l'image fixe au conteneur
# (VALEURS_IMPOSEES) et les noms que l'écrivain de .env de Hermes refuse lui-même (hermes_cli/config.py:62-117,
# « influence subprocess execution or Hermes runtime location »), moins les clés que la portée gérée épingle
# (celles-là, SECU-1 les retire).

SONDE_LISTE_DE_HERMES = r'''
from hermes_cli.config import _ENV_VAR_NAME_DENYLIST, _ENV_VAR_NAME_DENY_PREFIXES
resultat = {"noms": sorted(_ENV_VAR_NAME_DENYLIST), "prefixes": list(_ENV_VAR_NAME_DENY_PREFIXES)}
'''


def _famille_attendue(chemins) -> set:
    liste = executer_python(SONDE_LISTE_DE_HERMES, env=env_processus(chemins))
    assert "HERMES_HOME" in liste["noms"] and liste["prefixes"], liste  # sinon la source a changé : à relire
    noms = set(ad.VALEURS_IMPOSEES) | set(liste["noms"]) | {f"{p}ACP_PIEGE" for p in liste["prefixes"]}
    return noms - set(ad.valeurs_env_gere(ad.VALEURS_VIDES))


def _ecrire_famille(chemins, ou: str, noms) -> Path:
    dossier = chemins.hermes_home / "profiles" / "coder" if ou == "profil" else chemins.hermes_home
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / (".op.env" if ou == "op_env" else ".env")
    fichier.write_text("API_SERVER_KEY=0123456789abcdef0123456789\nOPENAI_API_KEY=legitime\n"
                       + "".join(f"{nom}=/nonexistent/acp-piege\n" for nom in sorted(noms)), encoding="utf-8")
    return fichier


@pytest.mark.parametrize("ou", ["env", "op_env", "profil"])
def test_variables_d_emplacement_et_d_execution_du_volume_refusees(chemins, valeurs, env_valide, ou):
    """Chaque nom de la famille, posé dans un fichier d'environnement du volume, refuse le démarrage (crochet,
    05-acp) et la relance ; les clés ordinaires (API_SERVER_KEY écrite par l'image, clés de fournisseur) restent
    admises."""
    installer_home_de_test(chemins, valeurs)
    attendues = _famille_attendue(chemins)
    fichier = _ecrire_famille(chemins, ou, attendues)
    trouvees = {nom for f, nom, _ in ad.variables_interdites_dans_le_volume(chemins) if f == fichier}
    print(json.dumps({"attendues": sorted(attendues), "trouvees": sorted(trouvees)}, ensure_ascii=False))
    assert not trouvees & {"API_SERVER_KEY", "OPENAI_API_KEY"}, trouvees
    assert sorted(attendues - trouvees) == [], f"non refusées : {', '.join(sorted(attendues - trouvees))}"
    for refuser in (ad.commande_verifier_relance, lambda c: ad.commande_gardes(c, env_valide),
                    lambda c: ad.commande_donnees(c, env_valide)):
        with pytest.raises(ad.Refus) as refus:
            refuser(chemins)
        assert f"{fichier} définit la variable interdite HERMES_HOME" in str(refus.value)


def test_la_copie_d_acp_contient_la_liste_de_l_ecrivain_de_hermes(chemins):
    """Garde de dérive (ajoutée avec le correctif) : la copie d'ACP de la liste que l'écrivain de .env de Hermes
    refuse (hermes_cli/config.py:62-117) contient celle de la version épinglée ; une montée de Hermes qui
    l'allonge fait échouer ce test au lieu d'ouvrir un trou silencieux."""
    liste = executer_python(SONDE_LISTE_DE_HERMES, env=env_processus(chemins))
    assert sorted(set(liste["noms"]) - ad.NOMS_REFUSES_PAR_L_ECRIVAIN_DE_HERMES) == []
    assert set(liste["prefixes"]) <= set(ad.PREFIXES_REFUSES_PAR_L_ECRIVAIN_DE_HERMES), liste["prefixes"]


# Relecture finale de P9 (constat securite-1) : garde de dérive des fichiers d'environnement. SECU-1 et la garde de
# la famille d'emplacement n'inspectent que FICHIERS_ENV_HERMES (.env, .op.env), recopiés de load_hermes_dotenv
# (Hermes 0.21.5, hermes_cli/env_loader.py:424-447). Une release qui chargerait un fichier de plus depuis
# HERMES_HOME avant la portée gérée rouvrirait en silence ce que SECU-1 ferme. La sonde relève, dans un processus
# neuf, chaque chemin du HERMES_HOME dont load_hermes_dotenv teste l'existence et chaque fichier qu'il charge.
SONDE_FICHIERS_DE_HERMES = r'''
import os, pathlib
home = pathlib.Path(os.environ["HERMES_HOME"]).resolve()
vus, charges = set(), []
def _sous_home(p):
    try:
        r = pathlib.Path(p).resolve()
    except OSError:
        return None
    return r.relative_to(home).as_posix() if (r == home or home in r.parents) else None
_existe = pathlib.Path.exists
def _existe_releve(self, *a, **k):
    rel = _sous_home(self)
    if rel is not None:
        vus.add(rel)
    return _existe(self, *a, **k)
pathlib.Path.exists = _existe_releve
from hermes_cli import env_loader
_charger = env_loader._load_dotenv_with_fallback
def _charger_releve(path, *a, **k):
    rel = _sous_home(path)
    if rel is not None:
        charges.append(rel)
    return _charger(path, *a, **k)
env_loader._load_dotenv_with_fallback = _charger_releve
try:
    env_loader.load_hermes_dotenv(load_external_secrets=False)
finally:
    pathlib.Path.exists = _existe
resultat = {"vus": sorted(vus), "charges": charges}
'''

# Chemins du HERMES_HOME que l'import et l'appel de load_hermes_dotenv sondent sans les charger comme fichiers
# d'environnement, relevés sur Hermes 0.21.5 le 9 octobre 2026 (journal de P9, relecture finale) : « .managed »,
# marqueur d'une installation tenue par un gestionnaire de paquets, lu en texte (hermes_constants.py,
# get_managed_system) ; « SOUL.md », persona du profil. Ni l'un ni l'autre ne publie de variable.
SONDES_ADMISES_HORS_ENV: frozenset = frozenset({".managed", "SOUL.md"})


def _ecarts_fichiers_de_hermes(releve: dict, attendus) -> list:
    ecarts = []
    if releve["charges"] != list(attendus):
        ecarts.append(f"fichiers chargés depuis HERMES_HOME : {releve['charges']}, attendus {list(attendus)}")
    inconnus = sorted(set(releve["vus"]) - set(attendus) - SONDES_ADMISES_HORS_ENV)
    if inconnus:
        ecarts.append(f"chemins du HERMES_HOME sondés par load_hermes_dotenv, inconnus de SECU : {inconnus}")
    return ecarts


def test_hermes_ne_charge_que_les_fichiers_d_environnement_que_secu_inspecte(chemins, valeurs):
    installer_home_de_test(chemins, valeurs)
    for nom in ad.FICHIERS_ENV_HERMES:
        fichier = chemins.hermes_home / nom
        if not fichier.exists():
            fichier.write_text("OPENAI_API_KEY=legitime\n", encoding="utf-8")
    env = env_processus(chemins)
    env.pop("OP_SERVICE_ACCOUNT_TOKEN", None)  # sinon Hermes saute .op.env (env_loader.py:442)
    releve = executer_python(SONDE_FICHIERS_DE_HERMES, env=env)
    print(json.dumps(releve, ensure_ascii=False))
    assert _ecarts_fichiers_de_hermes(releve, ad.FICHIERS_ENV_HERMES) == []


def test_la_garde_des_fichiers_d_environnement_nomme_un_fichier_de_plus():
    """Témoin de la garde ci-dessus : un fichier chargé ou sondé que SECU n'inspecte pas est nommé."""
    juste = {"vus": [".env", ".op.env"], "charges": [".env", ".op.env"]}
    assert _ecarts_fichiers_de_hermes(juste, (".env", ".op.env")) == []
    assert _ecarts_fichiers_de_hermes(juste, (".env",)) == [
        "fichiers chargés depuis HERMES_HOME : ['.env', '.op.env'], attendus ['.env']",
        "chemins du HERMES_HOME sondés par load_hermes_dotenv, inconnus de SECU : ['.op.env']"]
    sonde = {"vus": [".env", ".op.env", ".secrets.env"], "charges": [".env", ".op.env"]}
    assert _ecarts_fichiers_de_hermes(sonde, (".env", ".op.env")) == [
        "chemins du HERMES_HOME sondés par load_hermes_dotenv, inconnus de SECU : ['.secrets.env']"]


def test_un_env_du_volume_illisible_comme_hermes_refuse(chemins, valeurs):
    """Corollaire du correctif (non montré rouge) : la garde lit le fichier comme SECU-1 ; un .env en UTF-32,
    que Hermes ne sait pas lire, refuse au lieu d'être lu à moitié."""
    installer_home_de_test(chemins, valeurs)
    (chemins.hermes_home / ".op.env").write_bytes("A=1\n".encode("utf-32"))
    with pytest.raises(ad.Refus, match="UTF-32"):
        ad.refuser_variables_du_volume(chemins)


SONDE_PUBLICATION = r'''
import json, os
NOMS = json.loads(%(noms)r)
from hermes_cli.env_loader import load_hermes_dotenv
load_hermes_dotenv()
resultat = sorted(n for n in NOMS if os.environ.get(n) == "/nonexistent/acp-piege")
'''


def test_temoin_hermes_publie_la_famille_depuis_le_env_du_volume(chemins, valeurs):
    """Témoin (comportement de Hermes, sans garde ; vert avant comme après le correctif) : le chargement réel
    publie chaque nom de la famille posé dans /opt/data/.env, que la portée gérée ne recouvre pas."""
    installer_home_de_test(chemins, valeurs)
    attendues = _famille_attendue(chemins)
    _ecrire_famille(chemins, "env", attendues)
    publiees = executer_python(SONDE_PUBLICATION % {"noms": json.dumps(sorted(attendues))},
                               env=env_processus(chemins))
    assert sorted(attendues - set(publiees)) == [], sorted(attendues - set(publiees))


SONDE_HOME = r'''
import json, os
from hermes_cli.env_loader import load_hermes_dotenv
from hermes_constants import get_hermes_home
load_hermes_dotenv()
apres_un = str(get_hermes_home())
load_hermes_dotenv()
resultat = {"home_apres_un_chargement": apres_un, "temoin_lu_au_second": os.environ.get("ACP_TEMOIN_HOME")}
'''


def test_temoin_hermes_suit_le_home_du_env_du_volume(chemins, valeurs):
    """Témoin : HERMES_HOME posée dans /opt/data/.env devient le home de Hermes, et le chargement suivant lit le
    .env de ce répertoire, qu'aucune garde n'inspectait."""
    installer_home_de_test(chemins, valeurs)
    autre = chemins.hermes_home / "autre"
    autre.mkdir()
    (chemins.hermes_home / ".env").write_text(f"HERMES_HOME={autre}\n", encoding="utf-8")
    (autre / ".env").write_text("ACP_TEMOIN_HOME=lu\n", encoding="utf-8")
    resultat = executer_python(SONDE_HOME, env=env_processus(chemins))
    print(json.dumps(resultat, ensure_ascii=False))
    assert resultat == {"home_apres_un_chargement": str(autre), "temoin_lu_au_second": "lu"}, resultat


# Audit défensif, manque 2 : la garde de HERMES_MANAGED_DIR doit lire les fichiers comme Hermes (décodage et deux
# analyseurs), comme SECU-1 le fait pour les clés épinglées. HERMES_MANAGED_DIR ne peut pas être épinglée : rien ne
# rattrape une forme que la garde ne voit pas. Pour chaque forme, le témoin montre le chemin réel de Hermes qui la
# publie : le chargement (UTF-16 réécrit et NUL retiré : env_loader.py:347-370) ou « reload.env » (jetoniseur sur
# splitlines : agent/secret_scope.py:316-329, hermes_cli/config.py:2733-2747).
FORMES_MANAGED_DIR = {
    "nul": (lambda faux: f"HERMES_MANAGED\x00_DIR={faux}\n".encode("utf-8"), "chargement"),
    "utf16": (lambda faux: f"HERMES_MANAGED_DIR={faux}\n".encode("utf-16"), "chargement"),
    "saut_de_page": (lambda faux: f"ACP_X=1\x0cHERMES_MANAGED_DIR={faux}\n".encode("utf-8"), "reload_env"),
    "u2028": (lambda faux: f"ACP_X=1 HERMES_MANAGED_DIR={faux}\n".encode("utf-8"), "reload_env"),
}

SONDE_MANAGED_DIR = r'''
import os
from hermes_cli.env_loader import load_hermes_dotenv
from hermes_cli import config
load_hermes_dotenv()
if %(reload)r:
    config.reload_env()
resultat = os.environ.get("HERMES_MANAGED_DIR")
'''


@pytest.mark.parametrize("forme", sorted(FORMES_MANAGED_DIR))
def test_hermes_managed_dir_sous_les_formes_lues_par_hermes_est_refuse(chemins, valeurs, env_valide, forme):
    installer_home_de_test(chemins, valeurs)
    faux = chemins.hermes_home / "faux"
    encoder, chemin_de_hermes = FORMES_MANAGED_DIR[forme]
    fichier = chemins.hermes_home / ".env"
    fichier.write_bytes(encoder(faux))
    attendu = f"{fichier} définit la variable interdite HERMES_MANAGED_DIR"
    for refuser in (ad.refuser_variables_du_volume, ad.commande_verifier_relance,
                    lambda c: ad.commande_gardes(c, env_valide)):
        try:
            refuser(chemins)
        except ad.Refus as exc:
            assert attendu in str(exc), str(exc)
        else:
            pytest.fail(f"forme « {forme} » : aucun refus ({refuser})")
    # Témoin APRÈS les gardes (le chargement de Hermes réécrit le fichier) : Hermes publie bien la variable.
    publiee = executer_python(SONDE_MANAGED_DIR % {"reload": chemin_de_hermes == "reload_env"},
                              env=env_processus(chemins))
    assert publiee == str(faux), (forme, chemin_de_hermes, publiee)


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


@pytest.mark.parametrize("section, actives", [
    ({"command": {"enabled": True, "command": "id"}, "sources": ["command"]}, ["command"]),
    ({"onepassword": {"enabled": "oui"}, "bitwarden": {"enabled": False}}, ["onepassword"]),
    ({"bitwarden": {"enabled": False}, "onepassword": {"enabled": False}}, []),  # défauts de Hermes : admis
    ([{"command": "id"}], ["(section de type list)"]),
    (None, []),
    ({}, []),
])
def test_sources_de_secrets_actives(section, actives):
    assert ad.sources_de_secrets_actives(section) == actives


# ------------------------------------------------------------------ SECU-1 : le retrait lui-même


CLES_TEST = ["HERMES_BIN", "HERMES_TUI_TOOLSETS", "HTTP_PROXY"]


@pytest.mark.parametrize("brut, attendu, retirees", [
    (b"A=1\nHERMES_BIN=x\nB=2\n", "A=1\nB=2\n", ["HERMES_BIN"]),
    (b"export HERMES_BIN = x\nA=1\n", "A=1\n", ["HERMES_BIN"]),
    (b"'HERMES_BIN'=x\nA=1\n", "A=1\n", ["HERMES_BIN"]),  # clé citée : vue par python-dotenv seulement
    (b'A="x\nHERMES_BIN=y\n"\nB=2\n', 'A="x\n\n"\nB=2\n', ["HERMES_BIN"]),  # cachée dans une valeur multiligne
    (b"HERMES_\x00BIN=x\nA=1\n", "A=1\n", ["HERMES_BIN"]),  # NUL retiré par Hermes avant l'analyse
    (b"\xef\xbb\xbf  HERMES_BIN=x  \r\nA=1\r\n", "A=1\n", ["HERMES_BIN"]),
    ("HERMES_TUI_TOOLSETS=terminal\nA=1\n".encode("utf-16"), "A=1\n", ["HERMES_TUI_TOOLSETS"]),
    ("A=1\x85HERMES_BIN=x\nB=2\n".encode("utf-8"), "A=1\x85\nB=2\n", ["HERMES_BIN"]),  # séparateur de splitlines
    (b"A=\xe9\nHTTP_PROXY=http://x\n", "A=é\n", ["HTTP_PROXY"]),  # latin-1, comme Hermes
    (b"# HERMES_BIN=x\nA=HERMES_BIN=y\nMY_HTTP_PROXY=z\n", None, []),  # commentaire, valeur, autre clé : gardés
    (b"A=1\nB=2", None, []),
], ids=["simple", "export", "cle_citee", "multiligne", "nul", "bom_crlf", "utf16", "nel", "latin1", "intacts",
        "rien"])
def test_retirer_cles_env(brut, attendu, retirees):
    texte, enlevees = ad.retirer_cles_env(brut, CLES_TEST, Path("/opt/data/.env"))
    assert (texte, enlevees) == (attendu, retirees)
    if texte is not None:
        # Les deux analyseurs de Hermes ne voient plus aucune clé épinglée.
        import io

        from agent.secret_scope import _parse_env_text
        from dotenv import dotenv_values

        assert not set(_parse_env_text(texte)) & set(CLES_TEST)
        assert not set(dotenv_values(stream=io.StringIO(texte), interpolate=False)) & set(CLES_TEST)


def test_retirer_cles_env_refuse_l_utf32():
    with pytest.raises(ad.Refus, match="UTF-32"):
        ad.retirer_cles_env("HERMES_BIN=x\n".encode("utf-32"), CLES_TEST, Path("/opt/data/.env"))


def _arbre(chemin: Path) -> dict:
    return {str(p.relative_to(chemin)): (p.read_bytes() if p.is_file() and not p.is_symlink() else None,
                                        os.lstat(p).st_ino) for p in sorted(chemin.rglob("*"))}


def test_neutraliser_garde_le_reste_le_proprietaire_et_le_mode(chemins, valeurs):
    installer_home_de_test(chemins, valeurs)
    home = chemins.hermes_home
    fichiers = {
        home / ".env": "API_SERVER_KEY=0123456789abcdef0123456789\nHERMES_TUI_TOOLSETS=terminal\nOPENAI_API_KEY=sk\n",
        home / ".op.env": "OP_SERVICE_ACCOUNT_TOKEN=ops\nHERMES_SAFE_MODE=1\n",
        home / "profiles" / "coder" / ".env": "HERMES_BIN=/opt/data/faux\nANTHROPIC_API_KEY=a\n",
        home / "profiles" / "coder" / ".op.env": "A=1\n",
    }
    for fichier, contenu in fichiers.items():
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(contenu, encoding="utf-8")
        os.chown(fichier, UID_HERMES, UID_HERMES)
        os.chmod(fichier, 0o600)
    inode_intact = os.lstat(home / "profiles" / "coder" / ".op.env").st_ino
    rapport = ad.neutraliser_epingles_du_volume(chemins)
    assert [(str(f.relative_to(home)), c) for f, c in rapport] == [
        (".env", ["HERMES_TUI_TOOLSETS"]), (".op.env", ["HERMES_SAFE_MODE"]), ("profiles/coder/.env", ["HERMES_BIN"])]
    assert (home / ".env").read_text(encoding="utf-8") == (
        "API_SERVER_KEY=0123456789abcdef0123456789\nOPENAI_API_KEY=sk\n")
    assert (home / ".op.env").read_text(encoding="utf-8") == "OP_SERVICE_ACCOUNT_TOKEN=ops\n"
    assert (home / "profiles" / "coder" / ".env").read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=a\n"
    for fichier in fichiers:
        st = os.lstat(fichier)
        assert (st.st_uid, st.st_gid, st.st_mode & 0o7777) == (UID_HERMES, UID_HERMES, 0o600), fichier
    # Un fichier sans clé épinglée n'est pas réécrit ; aucun fichier temporaire ne reste ; idempotent.
    assert os.lstat(home / "profiles" / "coder" / ".op.env").st_ino == inode_intact
    assert not list(home.rglob(".*.acp-*"))
    avant = _arbre(home)
    assert ad.neutraliser_epingles_du_volume(chemins) == []
    assert _arbre(home) == avant


def test_neutraliser_ne_suit_aucun_lien(chemins, valeurs, tmp_path):
    """Un lien à la place d'un .env ou d'un profil est refusé ; une cible liée en dur n'est jamais modifiée (le
    nom est remplacé, pas l'inode) ; la portée gérée n'est jamais touchée."""
    installer_home_de_test(chemins, valeurs)
    home = chemins.hermes_home
    gere_avant = (chemins.dossier_gere / ".env").read_bytes()
    cible = tmp_path / "cible-root"
    cible.write_text("HERMES_BIN=/racine\n", encoding="utf-8")
    (home / ".env").symlink_to(cible)
    with pytest.raises(ad.Refus, match="sans suivre de lien"):
        ad.neutraliser_epingles_du_volume(chemins)
    (home / ".env").unlink()
    (home / "profiles").mkdir()
    (home / "profiles" / "intrus").symlink_to(chemins.dossier_gere, target_is_directory=True)
    with pytest.raises(ad.Refus, match="lien symbolique"):
        ad.neutraliser_epingles_du_volume(chemins)
    (home / "profiles" / "intrus").unlink()
    os.link(cible, home / ".env")
    assert ad.neutraliser_epingles_du_volume(chemins) == [(home / ".env", ["HERMES_BIN"])]
    assert cible.read_text(encoding="utf-8") == "HERMES_BIN=/racine\n"
    assert (home / ".env").read_text(encoding="utf-8") == ""
    assert (chemins.dossier_gere / ".env").read_bytes() == gere_avant


def test_neutraliser_exige_une_portee_geree_de_root(chemins, valeurs):
    installer_home_de_test(chemins, valeurs)
    (chemins.hermes_home / ".env").write_text("HERMES_BIN=x\n", encoding="utf-8")
    os.chown(chemins.dossier_gere / ".env", UID_HERMES, UID_HERMES)
    with pytest.raises(ad.Refus, match="doit être un fichier ordinaire de root"):
        ad.neutraliser_epingles_du_volume(chemins)
    (chemins.dossier_gere / ".env").unlink()
    with pytest.raises(ad.Refus, match="la portée gérée n'est pas installée"):
        ad.commande_verifier_relance(chemins)
    assert (chemins.hermes_home / ".env").read_text(encoding="utf-8") == "HERMES_BIN=x\n"


def test_journal_de_la_relance_nomme_les_cles_sans_valeur(chemins, valeurs, capsys):
    installer_home_de_test(chemins, valeurs, env="HERMES_TUI_TOOLSETS=valeur-secrete-de-test\nA=1\n")
    ad.commande_verifier_relance(chemins)
    sortie = capsys.readouterr().out
    assert (f"[acp] SECU-1 (relance) : {chemins.hermes_home / '.env'} portait 1 clé(s) épinglée(s) par la portée "
            "gérée (HERMES_TUI_TOOLSETS) : retirées, valeurs jamais affichées.") in sortie
    assert "valeur-secrete-de-test" not in sortie


def test_diagnostiquer_signale_les_cles_epinglees_sans_ecrire(chemins, valeurs):
    installer_home_de_test(chemins, valeurs, env="HERMES_SAFE_MODE=1\n")
    (chemins.hermes_home / ".op.env").write_text("HTTPS_PROXY=http://127.0.0.1:9\n", encoding="utf-8")
    avant = _arbre(chemins.hermes_home)
    assert ad.cles_epinglees_dans_le_volume(chemins) == [
        (chemins.hermes_home / ".env", ["HERMES_SAFE_MODE"]), (chemins.hermes_home / ".op.env", ["HTTPS_PROXY"])]
    infos, constats = ad.diagnostic(chemins)
    assert any("porte 1 clé(s) épinglée(s) (HERMES_SAFE_MODE)" in i for i in infos)
    assert not any("HERMES_SAFE_MODE" in c for c in constats)
    assert _arbre(chemins.hermes_home) == avant
