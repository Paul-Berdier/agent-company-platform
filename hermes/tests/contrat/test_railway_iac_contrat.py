"""Contrat entre l'infrastructure Railway déclarée (.railway/railway.ts) et les deux images.

Le graphe est celui que produit .railway/verifier.mjs en évaluant railway.ts avec des libellés
d'ESSAI (essai-hermes-acp, essai-identite-acp), comme le fait la CLI Railway. Chaque image est
démarrée avec EXACTEMENT les variables que ce graphe déclare, plus les variables que Railway fournit
à tout déploiement (rw_full.txt:26151-26247, simulées ici), sur un volume nommé jetable monté au
chemin déclaré. Prouvé, sur les images réellement construites :

1. Hermes accepte les variables déclarées (aucune n'est refusée par ses gardes, PORT et
   RAILWAY_* compris), journalise le commit déployé, et le contrôle de santé déclaré répond 200
   sur le PORT déclaré avec l'hôte qu'emploie Railway (healthcheck.railway.app, rw_full.txt:29964) ;
   les six variables du canal de notification (étape P7) sont des preserve() : sans aucune valeur
   posée, le canal vaut « aucune » et Hermes démarre ;
2. Hermes, avec les variables du canal posées comme le fera le propriétaire (Telegram, ou ntfy),
   démarre sans refus ni jeton dans ses journaux, et sa passerelle publie le canal configuré : le
   greffon lit exactement les noms que railway.ts déclare (docs/refonte/railway.md § 14) ;
3. identite, avec les quatre variables preserve() posées comme le fera le propriétaire, démarre et
   répond de même à son contrôle de santé ;
4. identite SANS ces quatre variables (état juste après le premier apply) refuse de démarrer, en
   français, en les nommant : l'échec fermé attendu par la procédure (docs/refonte/railway.md § 4).

Pré-requis, en plus de ceux de conftest.py : Node.js ≥ 22 et `npm ci --ignore-scripts --prefix
.railway` (image.yml le fait avant ces tests). Sans eux, ces tests ÉCHOUENT ; ils ne sont jamais
ignorés.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from conftest import afficher, lancer
from pile_identite import EMAIL, NOM, UTILISATEUR, Pile, docker, journal, options_env

RACINE_DEPOT = Path(__file__).resolve().parents[3]
IAC = RACINE_DEPOT / ".railway"
# Hôte des contrôles de santé de Railway (rw_full.txt:29964-29968).
HOTE_SANTE = "healthcheck.railway.app"
SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
# Message de commit sur deux lignes, avec des caractères qu'un shell interpréterait : les gardes ne
# doivent ni l'évaluer ni s'y arrêter (Railway le fournit tel quel).
MESSAGE = "Merge pull request #15 from Paul-Berdier/refonte/hermes-p2\n\nessai « $HOME » `id` ; $(id)"
PRESERVEES = ["ACP_IDP_EMAIL", "ACP_IDP_MOT_DE_PASSE_ARGON2", "ACP_IDP_NOM", "ACP_IDP_UTILISATEUR"]
# Étape P7 : canal de notification de Hermes, déclaré par preserve() (cahier P7, correction K13).
PRESERVEES_HERMES = sorted(["ACP_NOTIFICATIONS", "ACP_TELEGRAM_JETON", "ACP_TELEGRAM_DISCUSSION", "ACP_NTFY_SERVEUR",
                            "ACP_NTFY_SUJET", "ACP_NTFY_JETON"])
# Valeurs que le propriétaire poserait dans Railway (docs/refonte/railway.md § 14) ; ici de TEST, jamais envoyées
# (aucune notification n'est en file au démarrage d'un volume neuf).
# Formes volontairement différentes des vrais jetons (ni « chiffres:… » de Telegram, ni « tk_… » de ntfy) : aucun
# balayage de secrets ne doit les prendre pour des jetons réels.
JETON_TELEGRAM_ESSAI = "jeton-telegram-essai-acp-jamais-journalise"
JETON_NTFY_ESSAI = "jeton-ntfy-essai-acp-jamais-journalise"
CANAUX_POSES = {
    "telegram": {"ACP_NOTIFICATIONS": "telegram", "ACP_TELEGRAM_JETON": JETON_TELEGRAM_ESSAI,
                 "ACP_TELEGRAM_DISCUSSION": "-1001234567890"},
    "ntfy": {"ACP_NOTIFICATIONS": "ntfy", "ACP_NTFY_SERVEUR": "https://ntfy.sh",
             "ACP_NTFY_SUJET": "acp-essai-sujet-0123456789", "ACP_NTFY_JETON": JETON_NTFY_ESSAI},
}
PYTHON = "/opt/hermes/.venv/bin/python"


@pytest.fixture(scope="module")
def graphe(tmp_path_factory) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.fail("Node.js (≥ 22) est introuvable : il évalue .railway/railway.ts comme la CLI Railway.",
                    pytrace=False)
    if not (IAC / "node_modules" / "railway").is_dir():
        pytest.fail("SDK absent : lancez d'abord `npm ci --ignore-scripts --prefix .railway`.", pytrace=False)
    fichier = tmp_path_factory.mktemp("iac") / "graphe-essai.json"
    resultat = subprocess.run(
        [node, "--experimental-strip-types", str(IAC / "verifier.mjs"), "--graphe", str(fichier)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    afficher("verifier.mjs (évaluation de railway.ts)", resultat.stdout + resultat.stderr)
    assert resultat.returncode == 0, "railway.ts n'est pas conforme (voir la sortie de verifier.mjs)."
    return json.loads(fichier.read_text(encoding="utf-8"))


def service(graphe: dict, nom: str) -> dict:
    return next(r for r in graphe["projet"]["resources"] if r.get("address") == f"service.{nom}")


def variables(noeud: dict) -> Tuple[Dict[str, str], List[str]]:
    """(variables littérales, noms des variables preserve()) d'un service du graphe."""
    litterales: Dict[str, str] = {}
    preservees: List[str] = []
    for cle, valeur in noeud.get("variables", {}).items():
        if valeur.get("type") == "literal":
            litterales[cle] = valeur["value"]
        elif valeur.get("type") == "preserve":
            preservees.append(cle)
        else:
            raise AssertionError(f"{cle} : type de variable inattendu {valeur!r}")
    return litterales, sorted(preservees)


def montage(noeud: dict) -> Tuple[str, str]:
    """(nom du volume, point de montage) du seul volume du service."""
    (attache,) = noeud["volumeAttachments"].values()
    return attache["volume"].split(".", 1)[1], attache["mountPath"]


def env_railway(graphe: dict, nom: str) -> Dict[str, str]:
    """Variables que Railway fournit à tout déploiement (rw_full.txt:26151-26247), simulées."""
    noeud = service(graphe, nom)
    volume, point = montage(noeud)
    libelle = graphe["libelles"]["LIBELLE_HERMES" if nom == "hermes" else "LIBELLE_IDENTITE"]
    (region,) = noeud["deploy"]["multiRegionConfig"]
    return {
        "RAILWAY_PUBLIC_DOMAIN": f"{libelle}.up.railway.app",
        "RAILWAY_PRIVATE_DOMAIN": f"{nom}.railway.internal",
        "RAILWAY_PROJECT_NAME": graphe["projet"]["name"],
        "RAILWAY_PROJECT_ID": "00000000-0000-4000-8000-00000000c0de",
        "RAILWAY_ENVIRONMENT_NAME": "production",
        "RAILWAY_ENVIRONMENT_ID": "00000000-0000-4000-8000-0000000e0e0e",
        "RAILWAY_SERVICE_NAME": nom,
        "RAILWAY_SERVICE_ID": f"00000000-0000-4000-8000-{'00000000beef' if nom == 'hermes' else '00000000cafe'}",
        "RAILWAY_REPLICA_ID": "00000000-0000-4000-8000-000000000001",
        "RAILWAY_REPLICA_REGION": region,
        "RAILWAY_DEPLOYMENT_ID": "00000000-0000-4000-8000-0000000d0d0d",
        "RAILWAY_SNAPSHOT_ID": "00000000-0000-4000-8000-000000005555",
        "RAILWAY_VOLUME_NAME": volume,
        "RAILWAY_VOLUME_MOUNT_PATH": point,
        "RAILWAY_GIT_COMMIT_SHA": SHA,
        "RAILWAY_GIT_AUTHOR": "Paul-Berdier",
        "RAILWAY_GIT_BRANCH": noeud["source"]["branch"],
        "RAILWAY_GIT_REPO_NAME": "agent-company-platform",
        "RAILWAY_GIT_REPO_OWNER": "Paul-Berdier",
        "RAILWAY_GIT_COMMIT_MESSAGE": MESSAGE,
    }


def test_hermes_demarre_avec_les_variables_de_railway_ts(graphe, ressources, image):
    noeud = service(graphe, "hermes")
    litterales, preservees = variables(noeud)
    # Étape P7 : seules les variables du canal de notification sont posées à la main (preserve()) ; ici, AUCUNE
    # n'est posée (état d'un propriétaire qui n'a pas encore choisi de canal) : canal « aucune », démarrage normal.
    assert preservees == PRESERVEES_HERMES
    assert montage(noeud)[1] == "/opt/data"
    env = {**litterales, **env_railway(graphe, "hermes")}
    afficher("variables de Hermes (railway.ts + Railway simulé)", json.dumps(env, ensure_ascii=False, indent=2))

    conteneur = lancer(ressources, image, env)  # volume jetable sur /opt/data, comme le graphe

    port, chemin = litterales["PORT"], noeud["deploy"]["healthcheckPath"]
    reponse = conteneur.executer(["curl", "-s", "-w", "\n%{http_code}", "-H", f"Host: {HOTE_SANTE}",
                                  f"http://127.0.0.1:{port}{chemin}"], verifier=True).stdout
    corps, _, code = reponse.rpartition("\n")
    afficher(f"santé de Hermes (Host: {HOTE_SANTE}, port {port})", reponse)
    assert code == "200"
    sante = json.loads(corps)
    assert sante.get("ok") is True and sante.get("auth_required") is True

    journaux = conteneur.journaux()
    assert f"[acp] commit déployé : {SHA}" in journaux
    assert (f"[acp] variables validées ; émetteur OIDC {litterales['HERMES_DASHBOARD_OIDC_ISSUER']}, client hermes-acp, "
            f"URL publique {litterales['HERMES_DASHBOARD_PUBLIC_URL']} (client public).") in journaux
    assert "REFUS" not in journaux
    # Aucune variable du canal posée : la passerelle publie « aucune », non configurée (jamais un canal inventé).
    canal = attendre_canal_publie(conteneur)
    afficher("canal publié par la passerelle (aucune variable du canal posée)", json.dumps(canal, ensure_ascii=False))
    assert canal == {"canal": "aucune", "configure": False, "serveur": None}


def canal_publie(conteneur) -> object:
    """État PUBLIC du canal que la passerelle écrit dans la base du greffon (jamais un jeton), ou None."""
    code = ("import sqlite3\n"
            "c = sqlite3.connect('file:/opt/data/plugin-data/acp-poste/data.db?mode=ro', uri=True)\n"
            "l = c.execute(\"SELECT valeur FROM emetteur WHERE cle = 'canal'\").fetchone()\n"
            "print(l[0] if l else 'null')\n")
    resultat = conteneur.executer([PYTHON, "-c", code], utilisateur="hermes", verifier=False)
    if resultat.returncode != 0:
        return None
    try:
        return json.loads(resultat.stdout.strip() or "null")
    except ValueError:
        return None


def attendre_canal_publie(conteneur, delai: float = 240) -> object:
    """La passerelle publie le canal à son enregistrement, puis à chaque passe de l'émetteur."""
    limite = time.monotonic() + delai
    dernier = None
    while time.monotonic() < limite:
        dernier = canal_publie(conteneur)
        if dernier:
            return dernier
        time.sleep(3)
    raise AssertionError(f"canal jamais publié par la passerelle après {delai:.0f} s (dernier état : {dernier!r})")


@pytest.mark.parametrize("canal", sorted(CANAUX_POSES))
def test_hermes_demarre_avec_le_canal_pose_dans_railway(graphe, ressources, image, canal):
    """Étape P7 (docs/refonte/railway.md § 14) : le propriétaire pose dans Railway les valeurs des variables que
    railway.ts déclare par preserve() ; Hermes démarre (aucun refus de ses gardes), ses journaux ne portent aucun
    jeton, et la passerelle publie le canal CONFIGURÉ : le greffon lit exactement les noms déclarés."""
    noeud = service(graphe, "hermes")
    litterales, preservees = variables(noeud)
    posees = CANAUX_POSES[canal]
    assert set(posees) <= set(preservees), "chaque variable posée par le propriétaire est déclarée par preserve()"
    env = {**litterales, **posees, **env_railway(graphe, "hermes")}

    conteneur = lancer(ressources, image, env)

    port, chemin = litterales["PORT"], noeud["deploy"]["healthcheckPath"]
    code = conteneur.executer(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-H", f"Host: {HOTE_SANTE}",
                               f"http://127.0.0.1:{port}{chemin}"], verifier=True).stdout.strip()
    assert code == "200"
    publie = attendre_canal_publie(conteneur)
    afficher(f"canal publié par la passerelle ({canal} posé)", json.dumps(publie, ensure_ascii=False))
    attendu = {"canal": canal, "configure": True,
               "serveur": posees["ACP_NTFY_SERVEUR"] if canal == "ntfy" else None}
    assert publie == attendu
    journaux = conteneur.journaux()
    assert "REFUS" not in journaux
    assert "notifications désactivées" not in journaux
    for secret in (JETON_TELEGRAM_ESSAI, JETON_NTFY_ESSAI, CANAUX_POSES["ntfy"]["ACP_NTFY_SUJET"]):
        assert secret not in journaux, "un jeton ou le sujet ntfy apparaît dans les journaux"


def test_identite_demarre_avec_les_variables_de_railway_ts(graphe, image_identite, empreinte_argon2):
    noeud = service(graphe, "identite")
    litterales, preservees = variables(noeud)
    assert preservees == PRESERVEES
    assert montage(noeud)[1] == "/config"
    # Valeurs que le propriétaire pose dans Railway (docs/refonte/railway.md § 5) ; ici de TEST.
    posees = {"ACP_IDP_UTILISATEUR": UTILISATEUR, "ACP_IDP_NOM": NOM, "ACP_IDP_EMAIL": EMAIL,
              "ACP_IDP_MOT_DE_PASSE_ARGON2": empreinte_argon2}
    env = {**litterales, **posees, **env_railway(graphe, "identite")}
    pile = Pile()
    try:
        nom = pile.lancer_identite(image_identite, env)  # volume jetable sur /config, santé attendue
        port, chemin = litterales["PORT"], noeud["deploy"]["healthcheckPath"]
        sante = docker("exec", nom, "wget", "-q", "-O", "-", "--header", f"Host: {HOTE_SANTE}",
                       f"http://127.0.0.1:{port}{chemin}", verifier=False)
        afficher(f"santé d'identite (Host: {HOTE_SANTE}, port {port})", f"code {sante.returncode} : {sante.stdout}")
        assert sante.returncode == 0 and json.loads(sante.stdout) == {"status": "OK"}
        texte = journal(nom)
        attendu = (f"[acp-identite] variables validées ; utilisateur unique configuré (identifiant non journalisé) ; "
                   f"émetteur https://{litterales['ACP_IDP_DOMAINE']} ; client hermes-acp → "
                   f"{litterales['ACP_HERMES_URL']}/auth/callback")
        assert attendu in texte
        assert f"« {UTILISATEUR} »" not in texte
        assert "REFUS" not in texte
        assert empreinte_argon2 not in texte
    finally:
        pile.nettoyer()


def test_identite_refuse_sans_les_variables_du_proprietaire(graphe, image_identite):
    """État juste après le premier `railway config apply` : preserve() ne crée aucune valeur ; le
    service doit refuser de démarrer (échec fermé), en nommant chaque variable à poser."""
    noeud = service(graphe, "identite")
    litterales, preservees = variables(noeud)
    env = {**litterales, **env_railway(graphe, "identite")}
    pile = Pile()
    try:
        volume = pile.volume()
        nom = pile.nom("identite-sans-variables")
        pile.conteneurs.append(nom)
        resultat = docker("run", "--name", nom, "-v", f"{volume}:/config", *options_env(env), image_identite,
                          verifier=False, delai=180)
        texte = resultat.stdout + resultat.stderr
        afficher("identite sans les variables du propriétaire", texte)
        assert resultat.returncode == 1
        for variable in preservees:
            assert f"[acp-identite] REFUS : la variable {variable} est obligatoire et absente (ou vide)." in texte
        assert "[acp-identite] Démarrage arrêté (échec fermé)." in texte
        # Rien n'a été écrit sur le volume : aucun secret généré avant la validation des variables.
        contenu = docker("run", "--rm", "-v", f"{volume}:/config", "--entrypoint", "/bin/sh", image_identite,
                         "-c", "ls -A /config").stdout.strip()
        assert contenu == "", f"/config n'est pas vide après un refus : {contenu!r}"
    finally:
        pile.nettoyer()
