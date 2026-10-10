"""Contrôle STATIQUE de l'infrastructure Railway d'ACP (``.railway/``), sans Node, sans compte ni réseau.

Lancé par la suite du dépôt (``python -m pytest``, volet « poste » de ci.yml, Linux et Windows).
L'évaluation réelle de ``railway.ts`` (typage ``tsc`` contre le SDK, refus des gabarits, graphe
attendu) est faite par ``.railway/verifier.mjs`` dans image.yml, et le démarrage des deux images
avec les variables qu'il déclare par ``hermes/tests/contrat/test_railway_iac_contrat.py``.

Ce qui est vérifié ici :
- SDK ``railway`` isolé dans ``.railway/`` et épinglé (version exacte, verrou npm haché) ;
- AUCUNE Start Command ni commande de pré-déploiement dans ``railway.ts`` ;
- réglages déclarés : constructeur Dockerfile, Serverless coupé, politique de redémarrage,
  limites, Wait for CI, santé, région, branche, répertoires racines, ports, volumes, preserve() ;
- libellés des sous-domaines : gabarit détecté (et garde de refus présente) ou libellé DNS valide,
  jamais d'hôte *.up.railway.app écrit en dur hors des constantes ;
- aucun secret ;
- cohérence avec les images (Dockerfiles, ports, points de montage, limite mémoire mesurée) ;
- CI : image.yml suit ``.railway/**``, évalue l'IaC et garde un groupe de concurrence par exécution
  hors PR, comme ci.yml ; l'étape finale d'image.yml échoue s'il restait des ressources de test ;
  ``.railway/**`` en LF ; aucun fichier Config as Code (railway.json / railway.toml).
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[2]
IAC = RACINE / ".railway"
RAILWAY_TS = IAC / "railway.ts"

VERSION_SDK = "3.11.0"
# Intégrité publiée par le registre npm pour railway@3.11.0 (npm view railway@3.11.0 dist.integrity,
# relevée le 25/09/2026) : le verrou doit porter exactement celle-ci.
INTEGRITE_SDK = (
    "sha512-ehLFHCxV+gITWeBlIVaXulXaVRg4LCxqm0bq64iXSwYL1DESd0pUeLYMP/BMBhnZWeFFBYyJCREaq+Nka7Wgmw=="
)
GABARITS = {"LIBELLE_HERMES": "<libellé-hermes>", "LIBELLE_IDENTITE": "<libellé-identite>"}
LIBELLE_DNS = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
# Variables posées par le propriétaire dans Railway, déclarées par preserve() : identité (P2) et, depuis P7, canal de
# notification de Hermes (Telegram ou ntfy, ACP_NOTIFICATIONS comprise : cahier P7, correction K13).
PRESERVEES_PAR_SERVICE = {
    "identite": ("ACP_IDP_UTILISATEUR", "ACP_IDP_NOM", "ACP_IDP_EMAIL", "ACP_IDP_MOT_DE_PASSE_ARGON2"),
    "hermes": ("ACP_NOTIFICATIONS", "ACP_TELEGRAM_JETON", "ACP_TELEGRAM_DISCUSSION", "ACP_NTFY_SERVEUR",
               "ACP_NTFY_SUJET", "ACP_NTFY_JETON"),
}
VARIABLES_PRESERVEES = tuple(v for noms in PRESERVEES_PAR_SERVICE.values() for v in noms)
# Nom qui désigne un secret : jamais un littéral dans railway.ts (même liste que .railway/verifier.mjs).
NOM_SECRET = re.compile(r"JETON|TOKEN|SECRET|KEY|CLE|PASSWORD|MOT_DE_PASSE|ARGON2|OAUTH", re.I)
FICHIERS_SUIVIS = (".gitignore", "package-lock.json", "package.json", "railway.ts", "tsconfig.json", "verifier.mjs")


def lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


def sans_commentaires(texte: str) -> str:
    """Code TypeScript sans commentaires ``//`` ni ``/* */`` (railway.ts n'a pas de ``//`` dans une
    chaîne hors des URL, traitées à part)."""
    texte = re.sub(r"/\*.*?\*/", "", texte, flags=re.S)
    return "\n".join(re.sub(r"(?<![:\"'])//.*$", "", ligne) for ligne in texte.splitlines())


@pytest.fixture(scope="module")
def code() -> str:
    return sans_commentaires(lire(RAILWAY_TS))


def constante(code_ts: str, nom: str) -> str:
    trouves = re.findall(rf'^const {nom} = "([^"\n]*)";$', code_ts, flags=re.M)
    assert len(trouves) == 1, f"railway.ts doit déclarer « const {nom} = \"…\"; » exactement une fois ({len(trouves)})."
    return trouves[0]


def evaluer_arithmetique(expression: str, noms: dict[str, int]) -> float:
    """Évalue une expression arithmétique simple (nombres, noms connus, + - * / **, int()), sans eval."""

    def valeur(noeud: ast.AST) -> float:
        if isinstance(noeud, ast.Expression):
            return valeur(noeud.body)
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)):
            return noeud.value
        if isinstance(noeud, ast.Name) and noeud.id in noms:
            return noms[noeud.id]
        if isinstance(noeud, ast.BinOp):
            gauche, droite = valeur(noeud.left), valeur(noeud.right)
            operations = {ast.Add: lambda: gauche + droite, ast.Sub: lambda: gauche - droite,
                          ast.Mult: lambda: gauche * droite, ast.Div: lambda: gauche / droite,
                          ast.Pow: lambda: gauche ** droite}
            if type(noeud.op) in operations:
                return operations[type(noeud.op)]()
        if (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) and noeud.func.id == "int"
                and len(noeud.args) == 1):
            return int(valeur(noeud.args[0]))
        raise AssertionError(f"expression non admise : {ast.dump(noeud)}")

    return valeur(ast.parse(expression, mode="eval"))


# --------------------------------------------------------------------------- SDK isolé et épinglé


def test_sdk_isole_et_epingle():
    paquet = json.loads(lire(IAC / "package.json"))
    assert paquet.get("private") is True
    assert paquet.get("type") == "module", "railway.ts est un module ES (import depuis railway/iac)."
    assert paquet.get("dependencies") == {"railway": VERSION_SDK}
    developpement = paquet.get("devDependencies") or {}
    assert list(developpement) == ["typescript"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", developpement["typescript"]), "typescript doit être épinglé exactement."
    assert "version" not in paquet, "paquet privé, non publié : aucune version à synchroniser."

    verrou = json.loads(lire(IAC / "package-lock.json"))
    assert verrou.get("lockfileVersion") == 3
    racine = verrou["packages"][""]
    assert racine.get("dependencies") == paquet["dependencies"]
    assert racine.get("devDependencies") == paquet["devDependencies"]
    sdk = verrou["packages"]["node_modules/railway"]
    assert sdk["version"] == VERSION_SDK
    assert sdk["integrity"] == INTEGRITE_SDK
    assert verrou["packages"]["node_modules/typescript"]["version"] == developpement["typescript"]
    for chemin, entree in verrou["packages"].items():
        if not chemin:
            continue
        assert entree.get("resolved", "").startswith("https://registry.npmjs.org/"), f"{chemin} : hors du registre npm."
        assert entree.get("integrity", "").startswith("sha512-"), f"{chemin} : intégrité sha512 absente."

    # Isolement : ni le workspace racine ni son verrou ne connaissent le SDK (le moteur gelé et
    # scripts/check_engine_frozen.py n'en sont pas affectés).
    racine_depot = json.loads(lire(RACINE / "package.json"))
    assert all(".railway" not in w for w in racine_depot.get("workspaces", []))
    verrou_racine = json.loads(lire(RACINE / "package-lock.json"))
    assert not any(c == "node_modules/railway" or c.startswith(".railway") for c in verrou_racine["packages"])


def test_liste_blanche_git_de_railway():
    lignes = [l.strip() for l in lire(IAC / ".gitignore").splitlines() if l.strip() and not l.startswith("#")]
    assert lignes[0] == "*", "tout est ignoré par défaut dans .railway/ (node_modules, copies d'essai, lien de projet)."
    assert sorted(l[1:] for l in lignes[1:]) == sorted(FICHIERS_SUIVIS)
    assert all(l.startswith("!") for l in lignes[1:])


def test_tsconfig_strict():
    configuration = json.loads(lire(IAC / "tsconfig.json"))
    options = configuration["compilerOptions"]
    assert options["strict"] is True and options["noEmit"] is True
    assert options["skipLibCheck"] is False, "les types du SDK sont vérifiés, pas ignorés."
    assert options.get("erasableSyntaxOnly") is True, "la CLI évalue railway.ts par simple suppression des types."
    assert configuration["files"] == ["railway.ts"]


# --------------------------------------------------------------------------- railway.ts


def test_import_unique_du_sdk(code):
    imports = re.findall(r'^import .* from "([^"]+)";$', code, flags=re.M)
    assert imports == ["railway/iac"]


def test_aucune_start_command(code):
    """Une Start Command remplace l'ENTRYPOINT (rw_full.txt:29497-29507), donc les gardes des deux
    images : aucune n'est déclarée, sous aucune des formes admises par le SDK."""
    interdits = {
        r"\bstart\s*:": "start",
        r"\bstartCommand\b": "startCommand",
        r"\brun\s*:": "run: { command }",
        r"\bpreDeploy(?:Command)?\b": "preDeploy",
        r"\bcronSchedule\b": "cronSchedule",
        r"\bconfigFile\b": "configFile",
        r"\bdomains\s*:": "domains (domaines générés hors IaC)",
        r"\bnetworking\s*:": "networking",
        r"\btcp(?:Proxies)?\s*:": "tcp",
    }
    trouves = [nom for motif, nom in interdits.items() if re.search(motif, code)]
    assert not trouves, f"railway.ts déclare {trouves} : interdit (docs/refonte/railway.md § 3)."


@pytest.mark.parametrize(("motif", "nombre"), [
    (r'builder: "DOCKERFILE"', 3),
    (r"sleepApplication: false", 3),
    (r'restartPolicyType: "ON_FAILURE"', 3),
    (r"restartPolicyMaxRetries: 10,", 2),
    (r"restartPolicyMaxRetries: 100,", 1),
    (r"limitOverride: \{ containers: \{ cpu: 1, memoryBytes: MEMOIRE_HERMES \} \}", 1),
    (r"limitOverride: \{ containers: \{ cpu: 0\.5, memoryBytes: MEMOIRE_IDENTITE \} \}", 1),
    (r"limitOverride: \{ containers: \{ cpu: 2, memoryBytes: MEMOIRE_EXECUTANT \} \}", 1),
    (r"checkSuites: true", 3),
    (r'healthcheck: "/api/health"', 2),
    (r"replicas: \{ \[REGION\]: 1 \}", 3),
    (r'volume\("[a-z-]+", \{ region: REGION \}\)', 3),
    (r'rootDirectory: "/"', 1),
    (r'RAILWAY_DOCKERFILE_PATH: "executant/Dockerfile"', 1),
    (r'RAILWAY_DEPLOYMENT_DRAINING_SECONDS: "90"', 1),
    (r'volumeMounts: \{ "/donnees": donneesExecutant \}', 1),
    (r'rootDirectory: "/hermes"', 1),
    (r'rootDirectory: "/identite"', 1),
    (r'PORT: "9119"', 1),
    (r'PORT: "9091"', 1),
    (r'RAILWAY_DOCKERFILE_PATH: "image/Dockerfile"', 1),
    (r'volumeMounts: \{ "/opt/data": donneesHermes \}', 1),
    (r'volumeMounts: \{ "/config": donneesIdentite \}', 1),
    (r'HERMES_DASHBOARD_OIDC_CLIENT_ID: "hermes-acp"', 1),
    (r'HERMES_DASHBOARD_OIDC_SCOPES: "openid profile email offline_access"', 1),
    (r"resources: \[hermes, identite, executant, donneesHermes, donneesIdentite, donneesExecutant\]", 1),
    (r"HERMES_DASHBOARD_PUBLIC_URL: urlHermes,", 1),
    (r"HERMES_DASHBOARD_OIDC_ISSUER: urlIdentite,", 1),
    (r"ACP_IDP_DOMAINE: domaineIdentite,", 1),
    (r"ACP_HERMES_URL: urlHermes,", 1),
    (r"source: github\(DEPOT, \{ branch: BRANCHE, ", 3),
])
def test_reglages_declares(code, motif, nombre):
    assert len(re.findall(motif, code)) == nombre, f"« {motif} » attendu {nombre} fois dans railway.ts."


# Branche déployée : décision du propriétaire du 9 octobre 2026 (D164), avec la fusion de 1.0.0 ; elle remplace celle
# du 25 septembre 2026 (refonte/hermes).
BRANCHE_DEPLOYEE = "main"


def test_constantes(code):
    assert constante(code, "DEPOT") == "Paul-Berdier/agent-company-platform"
    assert constante(code, "BRANCHE") == BRANCHE_DEPLOYEE, "branche déployée : décision du propriétaire (D164)."
    assert constante(code, "ENVIRONNEMENT") == "production"
    assert constante(code, "PROJET") == "ACP"


def test_le_verificateur_attend_la_meme_branche():
    """verifier.mjs écrit ses valeurs attendues indépendamment de railway.ts (« modification consciente de l'un et de
    l'autre, dans la même PR ») : un changement de branche déployée qui n'en toucherait qu'un est refusé ici, sans
    Node, en plus de l'évaluation d'image.yml."""
    trouves = re.findall(r'^const BRANCHE = "([^"\n]*)";$', lire(IAC / "verifier.mjs"), flags=re.M)
    assert trouves == [BRANCHE_DEPLOYEE], f"verifier.mjs : branche attendue {trouves}, décidée {BRANCHE_DEPLOYEE!r}."


def _branches_de_push(flux: str) -> list[str]:
    """Branches du déclencheur ``push`` d'un workflow (bloc « ␣␣push: / ␣␣␣␣branches: », motifs entre guillemets ou
    non), lues sans PyYAML."""
    bloc = re.search(r"^  push:\n    branches:\n((?:      - .+\n)+)", flux, flags=re.M)
    assert bloc, "déclencheur push sans liste de branches"
    return [ligne.strip()[2:].strip().strip('"') for ligne in bloc.group(1).splitlines()]


@pytest.mark.parametrize("workflow", ["ci.yml", "image.yml", "executant.yml", "desktop-ci.yml"])
def test_les_workflows_qu_attend_railway_tournent_sur_la_branche_deployee(workflow):
    """« Wait for CI » (railway.md § 9) attend les workflows GitHub Actions du commit poussé sur la branche déployée :
    chacun doit donc se déclencher sur un push vers elle, nommée telle quelle (D164 : ``main``). Sans cela, Railway
    déploierait un commit dont ce workflow n'a jamais rendu de verdict."""
    branches = _branches_de_push(lire(RACINE / ".github" / "workflows" / workflow))
    assert BRANCHE_DEPLOYEE in branches, f"{workflow} : push sur {branches}, sans la branche déployée."


def test_branches_de_push_ne_lit_que_le_push():
    """Témoin pur : la branche citée par ``pull_request`` seulement ne compte pas ; motifs entre guillemets lus."""
    flux = ('"on":\n  pull_request:\n    branches:\n      - main\n  push:\n    branches:\n      - "refonte/**"\n'
            '    paths:\n      - "VERSION"\n')
    assert _branches_de_push(flux) == ["refonte/**"]
    assert BRANCHE_DEPLOYEE not in _branches_de_push(flux)


def test_garde_du_projet_lie(code):
    """Relecture P2 : le fichier décrit un projet ENTIER ; évalué pour un autre projet lié, le plan y
    supprimerait tout. La garde refuse tout projet lié autre que « acp » (effet réel prouvé par
    .railway/verifier.mjs : « autre projet lié » et « projet lié inconnu »)."""
    assert "if (ctx.projectName !== PROJET) {" in code
    assert code.index("ctx.projectName !== PROJET") < code.index("ctx.environment !== ENVIRONNEMENT")
    assert 'return project(PROJET, {' in code
    verificateur = lire(IAC / "verifier.mjs")
    assert '"autre projet lié"' in verificateur and '"projet lié inconnu"' in verificateur
    # Identifiant de la page « Regions » (rw_full.txt:30283) ; repli "europe-west4" par PR seulement.
    assert constante(code, "REGION") in {"europe-west4-drams3a", "europe-west4"}


def bloc_service(code_ts: str, nom: str) -> str:
    """Texte de la déclaration ``service("<nom>", {…})`` de railway.ts."""
    return code_ts.split(f'service("{nom}", {{', 1)[1].split("\n  });", 1)[0]


def test_variables_du_proprietaire_en_preserve(code):
    preservees = re.findall(r"^\s*([A-Z][A-Z0-9_]*): preserve\(\),", code, flags=re.M)
    assert sorted(preservees) == sorted(VARIABLES_PRESERVEES)
    for nom in VARIABLES_PRESERVEES:
        assert len(re.findall(rf"\b{nom}\b", code)) == 1, f"{nom} n'apparaît qu'en preserve()."
    # Chacune dans SON service : l'identité dans « identite », le canal de notification dans « hermes ».
    for service, noms in PRESERVEES_PAR_SERVICE.items():
        bloc = bloc_service(code, service)
        assert sorted(re.findall(r"^\s*([A-Z][A-Z0-9_]*): preserve\(\),", bloc, flags=re.M)) == sorted(noms), service


def test_canal_de_notification_memes_noms_que_l_image(code):
    """Étape P7 (cahier P7 § 6.2, correction K13) : railway.ts déclare EXACTEMENT les variables du canal que lisent
    le greffon (``notifications.VARIABLES``, retirées de l'environnement par ``register()``) et la garde de
    démarrage de l'image (``erreurs_notifications``) ; un nom manquant ici serait supprimé au plan suivant une pose
    dans Railway, un nom en trop ne serait lu par personne."""
    declarees = sorted(PRESERVEES_PAR_SERVICE["hermes"])
    greffon = lire(RACINE / "hermes" / "plugins" / "acp-poste" / "noyau" / "notifications.py")
    trouve = re.search(r"^VARIABLES = \(([^)]*)\)", greffon, flags=re.M)
    assert trouve, "notifications.VARIABLES introuvable"
    assert sorted(re.findall(r'"([A-Z_]+)"', trouve.group(1))) == declarees
    paquet = lire(RACINE / "hermes" / "plugins" / "acp-poste" / "__init__.py")
    trouve = re.search(r"^VARIABLES_NOTIFICATION = \(([^)]*)\)", paquet, flags=re.M)
    assert trouve, "VARIABLES_NOTIFICATION introuvable dans le greffon"
    assert sorted(re.findall(r'"([A-Z_]+)"', trouve.group(1))) == declarees
    demarrage = lire(RACINE / "hermes" / "image" / "acp_demarrage.py")
    fonction = demarrage.split("def erreurs_notifications(", 1)[1].split("\ndef ", 1)[0]
    assert sorted(set(re.findall(r'"(ACP_[A-Z_]+)"', fonction))) == declarees
    # Le canal n'est jamais imposé par un littéral (le démarrage refuserait avant la pose du jeton).
    assert not re.search(r"ACP_NOTIFICATIONS\s*:\s*[\"'`]", code)


def test_aucun_secret_en_litteral(code):
    """Toute variable dont le nom désigne un secret est preserve() (identité, jetons du canal), jamais un littéral ;
    l'exécutant n'en a aucune (D92, test suivant)."""
    for nom, valeur in re.findall(r"^\s*([A-Z][A-Z0-9_]*):\s*(.+?),?\s*$", code, flags=re.M):
        if NOM_SECRET.search(nom):
            assert valeur.startswith("preserve()"), f"{nom} : « {valeur} » au lieu de preserve()."


def test_verificateur_et_ses_temoins_p7():
    """Le vérificateur évalue la règle « nom de secret ⇒ preserve() » dans tous les services et s'éprouve lui-même
    sur trois copies altérées (jeton en clair, canal littéral, variable omise) : son effet réel est mesuré en CI
    (image.yml) et en local (`npm run --prefix .railway verifier`)."""
    verificateur = lire(IAC / "verifier.mjs")
    assert "const NOM_SECRET = /JETON|TOKEN|SECRET|KEY|CLE|PASSWORD|MOT_DE_PASSE|ARGON2|OAUTH/i;" in verificateur
    assert "if (NOM_SECRET.test(cle)) {" in verificateur
    for nom in PRESERVEES_PAR_SERVICE["hermes"]:
        assert f'      "{nom}",' in verificateur, nom
    for titre in ('"jeton Telegram écrit en clair"', '"canal imposé par un littéral"',
                  '"variable du canal omise (le plan la supprimerait)"'):
        assert verificateur.count(titre) == 1, titre
    assert "await attendreEcart(" in verificateur


def test_libelles_gabarit_detectes(code):
    """Libellés des sous-domaines : soit le gabarit EXACT (échec fermé, garde de refus présente),
    soit un libellé DNS valide choisi par le propriétaire ; jamais d'hôte écrit en dur ailleurs."""
    libelles = {nom: constante(code, nom) for nom in GABARITS}
    for nom, valeur in libelles.items():
        if valeur == GABARITS[nom]:
            print(f"\n{nom} vaut encore le gabarit « {valeur} » : plan et apply refusent (échec fermé).")
        else:
            assert "<" not in valeur and ">" not in valeur, f"{nom} : gabarit altéré « {valeur} »."
            assert LIBELLE_DNS.fullmatch(valeur), f"{nom} : « {valeur} » n'est pas un libellé DNS."
    if libelles["LIBELLE_HERMES"] == libelles["LIBELLE_IDENTITE"]:
        pytest.fail("les deux services auraient le même sous-domaine.")
    # Garde de refus présente (son effet réel est prouvé par .railway/verifier.mjs en CI).
    assert 'valeur.includes("<") || valeur.includes(">")' in code
    assert "vaut encore le gabarit" in code
    assert "LIBELLE_DNS.test(valeur)" in code
    assert 'libelle("LIBELLE_HERMES", LIBELLE_HERMES)' in code
    assert 'libelle("LIBELLE_IDENTITE", LIBELLE_IDENTITE)' in code
    # Aucun hôte *.up.railway.app littéral : les domaines ne viennent que des constantes vérifiées.
    assert not re.search(r"[\"'`](?:https?://)?[a-z0-9-]+\.up\.railway\.app", code)
    assert len(re.findall(r"\}\.up\.railway\.app`", code)) == 2


def test_aucun_secret():
    motifs = [
        r"\$argon2", r"-----BEGIN", r"\bsk-[A-Za-z0-9_-]{8,}", r"\bgh[pousr]_[A-Za-z0-9]{16,}", r"github_pat_",
        r"\bAKIA[0-9A-Z]{12,}", r"\beyJ[A-Za-z0-9_-]{10,}\.", r"[A-Fa-f0-9]{40,}", r"[A-Za-z0-9+/]{48,}={0,2}",
        r"(?i)\b(?:password|secret|token)\s*[:=]\s*[\"'][^\"']+[\"']",
    ]
    for fichier in ("railway.ts", "package.json", "tsconfig.json"):
        texte = lire(IAC / fichier)
        for motif in motifs:
            assert not re.search(motif, texte), f"{fichier} : motif de secret {motif!r}."


# --------------------------------------------------------------------------- cohérence avec les images


def test_coherence_avec_les_images(code):
    # Chemin du Dockerfile : répertoire racine + RAILWAY_DOCKERFILE_PATH (hermes), Dockerfile par
    # défaut à la racine (identite).
    assert (RACINE / "hermes" / "image" / "Dockerfile").is_file()
    assert (RACINE / "identite" / "Dockerfile").is_file()
    dockerfile_hermes = lire(RACINE / "hermes" / "image" / "Dockerfile")
    assert "HERMES_DASHBOARD_PORT=9119" in dockerfile_hermes, "PORT de railway.ts = port du tableau de bord."
    assert re.search(r'^ENTRYPOINT \["/opt/acp/bin/acp-entree"\]$', dockerfile_hermes, flags=re.M)
    assert re.search(r'^CMD \["gateway", "run"\]$', dockerfile_hermes, flags=re.M)
    assert "address: 'tcp://0.0.0.0:9091/'" in lire(RACINE / "identite" / "configuration.yml")
    dockerfile_identite = lire(RACINE / "identite" / "Dockerfile")
    assert re.search(r'^ENTRYPOINT \["/opt/acp-identite/acp-identite-entree"\]$', dockerfile_identite, flags=re.M)
    assert not re.search(r"^CMD ", dockerfile_identite, flags=re.M)
    # Points de montage exigés par les gardes des images.
    assert re.search(r'^POINT_DE_MONTAGE = "/opt/data"$', lire(RACINE / "hermes" / "image" / "acp_demarrage.py"), flags=re.M)
    assert '"${RAILWAY_VOLUME_MOUNT_PATH-}" != /config' in lire(RACINE / "identite" / "acp-identite-entree")
    # Limite mémoire d'identite = limite MESURÉE par test_memoire_premier_facteur_concurrent.
    gio = 1024 ** 3
    ts = re.search(r"^const MEMOIRE_IDENTITE = (.+);$", code, flags=re.M)
    py = re.search(r"^LIMITE_MEMOIRE_OCTETS = (.+)$", lire(RACINE / "hermes" / "tests" / "contrat" / "test_identite.py"),
                   flags=re.M)
    assert ts and py
    assert evaluer_arithmetique(ts.group(1), {"GIO": gio}) == evaluer_arithmetique(py.group(1), {"GIO": gio}) == 2684354560
    hermes = re.search(r"^const MEMOIRE_HERMES = (.+);$", code, flags=re.M)
    assert hermes and evaluer_arithmetique(hermes.group(1), {"GIO": gio}) == 2 * gio


def test_executant_sans_port_ni_secret_ni_reference(code):
    """Étape P6 (cahier § 10.2) : le service « executant » n'a ni santé, ni PORT, ni preserve(), ni variable qui
    nomme un secret, ni référence vers un autre service ; son Dockerfile existe là où l'indique la variable, et la
    politique de l'exécutant vise l'origine publique de Hermes déclarée ici (même libellé)."""
    bloc = code.split('service("executant", {', 1)[1].split("\n  });", 1)[0]
    assert "healthcheck" not in bloc and "PORT" not in bloc and "preserve(" not in bloc
    assert not re.search(r"^\s*[A-Z_]*(?:JETON|TOKEN|SECRET|KEY|CLE|PASSWORD|OAUTH)[A-Z_]*:", bloc, flags=re.M)
    assert "${{" not in code, "aucune référence de variable entre services"
    assert (RACINE / "executant" / "Dockerfile").is_file()
    assert re.search(r'^ENTRYPOINT \["/usr/bin/tini", "-s", "--", "/opt/acp/bin/acp-entree-executant"\]$',
                     lire(RACINE / "executant" / "Dockerfile"), flags=re.M)
    assert re.search(r"^const MEMOIRE_EXECUTANT = 4 \* GIO;$", code, flags=re.M)
    politique = lire(RACINE / "executant" / "politique" / "executant.toml")
    assert f'origine = "https://{constante(code, "LIBELLE_HERMES")}.up.railway.app"' in politique


def test_aucun_fichier_config_as_code():
    """Un service géré par railway.json / railway.toml ne peut pas l'être par l'IaC, et ce fichier
    surchargerait les réglages du service (rw_infrastructure-as-code : « IaC vs Config as Code »)."""
    try:
        suivis = subprocess.run(["git", "ls-files"], cwd=RACINE, capture_output=True, text=True, encoding="utf-8",
                                check=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError) as erreur:
        pytest.fail(f"git ls-files indisponible : {erreur}")
    trouves = [f for f in suivis if Path(f).name in {"railway.json", "railway.toml"}]
    assert not trouves, f"fichiers Config as Code suivis : {trouves}"


# --------------------------------------------------------------------------- CI et fins de ligne


def test_ci_image_evalue_l_iac():
    flux = lire(RACINE / ".github" / "workflows" / "image.yml")
    assert flux.count('- ".railway/**"') == 2, "image.yml doit suivre .railway/** en push et en PR."
    assert "npm ci --ignore-scripts --prefix .railway" in flux
    assert "npm run --prefix .railway verifier" in flux
    # Correction R2-1 : hors PR, un groupe PAR EXÉCUTION, jamais annulé ni remplacé (Wait for CI
    # ignore un run annulé dès qu'un autre workflow a réussi : rw_full.txt:29704-29707).
    assert ("group: image-${{ github.event_name == 'pull_request' && github.ref || github.run_id }}" in flux)
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in flux
    assert "cancel-in-progress: true" not in flux
    # L'IaC est évaluée AVANT les tests de contrat, qui lisent son graphe d'essai.
    assert flux.index("npm run --prefix .railway verifier") < flux.index("python -m pytest -s -v -rA hermes/tests/contrat")


def test_ci_yml_n_annule_aucun_run_hors_pr():
    """Relecture P2 : « Wait for CI » ignore un run annulé dès qu'un autre workflow du commit a réussi
    (rw_full.txt:29704-29707). ci.yml compte pour le déploiement (railway.md § 9) : hors PR, il ne
    doit donc jamais annuler ni remplacer un run, comme image.yml (groupe par exécution)."""
    flux = lire(RACINE / ".github" / "workflows" / "ci.yml")
    assert "group: ci-${{ github.event_name == 'pull_request' && github.ref || github.run_id }}" in flux
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in flux
    assert "cancel-in-progress: true" not in flux


def _travaux_d_image_yml() -> dict:
    """Texte de chaque job d'image.yml, par identifiant (lignes « ␣␣<id>: » sous « jobs: »)."""
    flux = lire(RACINE / ".github" / "workflows" / "image.yml")
    bloc = flux[flux.index("\njobs:\n") + len("\njobs:\n"):]
    morceaux = re.split(r"^  ([A-Za-z0-9_-]+):\n", bloc, flags=re.M)
    return dict(zip(morceaux[1::2], morceaux[2::2]))


def test_image_yml_echoue_s_il_reste_des_ressources_de_test():
    """Relecture P2 : l'étape finale nettoie puis ÉCHOUE si des ressources acp-contrat-* restaient. Étape P9 : CHAQUE
    job qui lance des tests de contrat ou navigateur (Docker) a sa propre étape finale, bornée à ce job."""
    travaux = _travaux_d_image_yml()
    avec_docker = [nom for nom, texte in travaux.items()
                   if re.search(r"python -m pytest[^\n]*hermes/tests/(contrat|e2e)", texte)]
    assert "image" in avec_docker and "restauration" in avec_docker, sorted(travaux)
    for nom in avec_docker:
        texte = travaux[nom]
        debut = texte.index("- name: Aucun conteneur, volume ni réseau de test ne reste")
        fin = texte.find("\n      - name: ", debut + 1)
        etape = texte[debut:fin if fin != -1 else len(texte)]
        assert "if: always()" in etape.splitlines()[1], nom
        for nettoyage in ("docker rm -f -v $reste", "docker volume rm -f $volumes", "docker network rm $reseaux"):
            assert nettoyage in etape, (nom, nettoyage)
        assert etape.count("restes=1") == 3, nom
        assert 'if [ "$restes" -ne 0 ]; then' in etape and "exit 1" in etape, nom
        # Dernière étape du job : rien ne peut s'exécuter après le contrôle.
        assert fin == -1, nom


def test_image_yml_selectionne_les_tests_de_restauration_par_job():
    """Étape P9 (cahier § 3.7) : marqueurs déclarés (--strict-markers) ; le job « image » désélectionne
    « restauration » et « montee », le job « restauration » ne lance qu'eux ; rien n'est ignoré en silence."""
    for ini in ("contrat", "e2e"):
        texte = lire(RACINE / "hermes" / "tests" / ini / "pytest.ini")
        assert "--strict-markers" in texte and re.search(r"^    restauration: ", texte, flags=re.M), ini
        assert re.search(r"^    montee: ", texte, flags=re.M), ini
    travaux = _travaux_d_image_yml()
    lancements = {nom: re.findall(r"python -m pytest[^\n]*hermes/tests/(?:contrat|e2e)[^\n]*", texte)
                  for nom, texte in travaux.items()}
    assert lancements["image"] and all(l.endswith('-m "not restauration and not montee"')
                                       for l in lancements["image"]), lancements["image"]
    assert sorted(lancements["restauration"]) == [
        "python -m pytest -s -v -rA hermes/tests/contrat -m restauration",
        "python -m pytest -s -v -rA hermes/tests/e2e -m restauration"], lancements["restauration"]
    assert 'ACP_E2E_OBLIGATOIRE: "1"' in travaux["restauration"]
    assert "timeout-minutes: 90" in travaux["restauration"]
    # Le job « montee » ne lance que les tests de montée (cahier § 5.6).
    assert lancements["montee"] == ["python -m pytest -s -v -rA hermes/tests/contrat -m montee"], lancements["montee"]


def test_image_yml_montee_de_donnees_a_la_main_seulement():
    """Étape P9 (cahier § 5.6, décision P9-4) : job « montee » sur workflow_dispatch seulement, entrée ref_avant lue une
    fois comme variable et validée ; quand elle est donnée, les jobs « image » et « restauration » ne tournent pas ; les
    images « avant » viennent d'une copie de travail détachée de ref_avant, sous les noms que lit le test ; le résumé
    dit « migration de schéma : … » même quand le test n'a rien écrit."""
    flux = lire(RACINE / ".github" / "workflows" / "image.yml")
    entree = flux[flux.index("  workflow_dispatch:\n"):flux.index("  pull_request:\n")]
    assert "      ref_avant:\n" in entree and entree.count('default: ""') == 2
    travaux = _travaux_d_image_yml()
    montee = travaux["montee"]
    assert "    if: github.event_name == 'workflow_dispatch' && inputs.ref_avant != ''\n" in montee
    for nom in ("image", "restauration"):
        assert "    if: github.event_name != 'workflow_dispatch' || inputs.ref_avant == ''\n" in travaux[nom], nom
    assert flux.count("${{ inputs.ref_avant }}") == 1 and "      REF_AVANT: ${{ inputs.ref_avant }}\n" in montee
    assert "fetch-depth: 0" in montee and "timeout-minutes: 90" in montee
    assert r'[[ "$REF_AVANT" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$ ]] || [[ "$REF_AVANT" == *..* ]]' in montee
    assert montee.count("exit 2") == 3
    assert 'git worktree add --detach "$ACP_RACINE_AVANT" "$avant"' in montee
    test = lire(RACINE / "hermes" / "tests" / "contrat" / "test_montee_de_donnees.py")
    for variable in ("ACP_IMAGE_TESTS_AVANT", "ACP_IMAGE_EXECUTANT_FACTICE_AVANT", "ACP_IMAGE_TESTS",
                     "ACP_IMAGE_EXECUTANT_FACTICE", "ACP_RACINE_AVANT", "ACP_MONTEE_DOSSIER"):
        assert f"      {variable}: " in montee and f'"{variable}"' in test, variable
    assert '--build-arg IMAGE_ACP="$ACP_IMAGE_AVANT"' in montee and '-t "$ACP_IMAGE_TESTS_AVANT"' in montee
    assert '-t "$ACP_IMAGE_EXECUTANT_FACTICE_AVANT" "$ACP_RACINE_AVANT"' in montee
    resume = montee[montee.index("- name: Migration de schéma (résumé du job)"):]
    assert resume.splitlines()[1].strip() == "if: always()"
    assert '"$ACP_MONTEE_DOSSIER/resume.md"' in resume and "migration de schéma : inconnue" in resume
    assert 'f"migration de schéma : {' in test


def test_railway_en_lf():
    assert re.search(r"^\.railway/\*\* text=auto eol=lf$", lire(RACINE / ".gitattributes"), flags=re.M)
