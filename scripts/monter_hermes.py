#!/usr/bin/env python3
"""Montée de version de Hermes Agent : relevé, écriture et inventaire de l'épinglage (cahier P9 § 5.2).

Source unique de l'épinglage : ``hermes/contrat/HERMES_VERSION``. Sous-commandes :

``verifier [--etiquette vAAAA.M.J]``
    Relève, SANS RIEN ÉCRIRE, ce que publie l'amont pour l'étiquette (par défaut celle épinglée) : condensat
    d'index et par plate-forme (``docker buildx imagetools inspect``), commit de l'étiquette (``git ls-remote``),
    puis, dans l'image tirée PAR CONDENSAT : ``hermes --version``, provenance de l'image, OpenRPC de la passerelle,
    ``LICENSE`` et noms des skills livrées. Rend ensuite chaque épingle forte à partir de ce relevé et la compare,
    octet pour octet, au fichier du dépôt : c'est la répétition à blanc de la montée (« Aucun écart » sur la
    version épinglée prouve que ``ecrire`` ne changerait rien).
``ecrire vAAAA.M.J [--date "2 octobre 2026"]``
    Refuse si un fichier cible porte des changements non committés ; réécrit les épingles fortes (liste
    ``EPINGLES_FORTES``) en LF ; rapporte les méthodes OpenRPC ajoutées et retirées, le changement
    d'``info.version`` (il coupe la Discussion du desktop), les skills livrées à classer à la main face à
    ``livrees.noms`` du verrou du catalogue, la borne ``requires_hermes`` du greffon (jamais modifiée ici), puis
    l'inventaire des anciennes valeurs. Idempotent : un second passage ne change rien. La date du relevé n'est
    changée que si une valeur relevée change.
``inventaire``
    ``git grep`` des valeurs épinglées (version, étiquette, commit, préfixe du condensat) en quatre groupes :
    épingles fortes (écrites par ``ecrire``), fixtures et tests (faux serveurs, travail humain), citations
    (commentaires « Hermes 0.21.5 … fichier:ligne », à revérifier dans la PR de montée), documentation
    (historique, jamais réécrite).
``derniere``
    Dernière release publiée à la fois en étiquette git amont et en étiquette Docker Hub (API publique), au
    format ``vAAAA.M.J[.N]`` ; n'écrit rien (veille mensuelle).

Toute valeur (lue dans HERMES_VERSION, relevée chez l'amont, ou passée par ``--date``) est validée dans sa forme
AVANT d'être passée à ``docker`` ou ``git`` ou d'être écrite ; un fichier absent, non UTF-8 ou un JSON abîmé est un
refus nommé.

Codes de sortie : 0 (aucun écart, ou écriture faite), 1 (écarts constatés), 2 (refus). N'exécute JAMAIS
``hermes update``, ne pousse rien, ne touche ni Railway ni les tests. Bibliothèque standard, ``docker`` et ``git``
sur l'hôte ; refus en français. Les commandes externes passent par un exécuteur injectable
(``scripts/tests/test_monter_hermes.py`` n'appelle ni Docker ni le réseau).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import difflib
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

RACINE = Path(__file__).resolve().parents[1]

IMAGE = "nousresearch/hermes-agent"
DEPOT_AMONT = "https://github.com/NousResearch/hermes-agent"
HOTE_DOCKER_HUB = "hub.docker.com"
CHEMIN_API_DOCKER_HUB = "/v2/repositories/nousresearch/hermes-agent/tags"
API_DOCKER_HUB = f"https://{HOTE_DOCKER_HUB}{CHEMIN_API_DOCKER_HUB}?page_size=100&name=v"
# Une page réelle de 100 étiquettes pèse de l'ordre de 100 Ko (relevé du 02/10/2026) : borne large, mais une borne.
LIMITE_PAGE = 4 * 1024 * 1024
CHEMIN_OPENRPC_IMAGE = "/opt/hermes/apps/shared/src/gateway-contract.openrpc.json"
CHEMIN_LICENCE_IMAGE = "/opt/hermes/LICENSE"
CHEMIN_PROVENANCE_IMAGE = "/etc/hermes/image-provenance.json"
HERMES_IMAGE_BIN = "/opt/hermes/.venv/bin/hermes"
PYTHON_IMAGE = "/opt/hermes/.venv/bin/python"

# Formes exigées AVANT tout usage d'une valeur (argument de docker ou de git, ou texte réécrit dans un fichier) :
# chiffres ASCII seulement (re.ASCII), aucun espace, aucun saut de ligne, jamais de tiret en tête.
FORME_ETIQUETTE = re.compile(r"v(\d{4})\.(\d{1,2})\.(\d{1,2})(?:\.(\d+))?", re.ASCII)
FORME_VERSION = re.compile(r"\d+\.\d+\.\d+", re.ASCII)
FORME_CONDENSAT = re.compile(r"sha256:[0-9a-f]{64}")
FORME_COMMIT = re.compile(r"[0-9a-f]{40}")
FORME_IMAGE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+")
# info.version de l'OpenRPC : écrite entre guillemets (fixture JSON), entre accents graves (README) et après « = ».
FORME_INFO_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,31}")
SORTIE_VERSION = re.compile(r"Hermes Agent v(?P<version>\S+) \((?P<date>[^)]+)\)(?: · upstream (?P<amont>[0-9a-f]+))?")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre")
# Date du relevé, en toutes lettres comme date_du_jour() l'écrit (« 2 octobre 2026 ») : c'est la seule forme que
# relisent la provenance du README du contrat (rendre) et la concordance (scripts/tests/test_epingles_hermes.py).
FORME_DATE = re.compile(rf"(?:[1-9]|[12][0-9]|3[01]) (?:{'|'.join(MOIS)}) [0-9]{{4}}")
FORMES_EPINGLE = {
    "HERMES_VERSION": FORME_VERSION, "HERMES_TAG": FORME_ETIQUETTE, "HERMES_COMMIT": FORME_COMMIT,
    "HERMES_IMAGE": FORME_IMAGE, "HERMES_IMAGE_INDEX": FORME_CONDENSAT, "HERMES_IMAGE_LINUX_AMD64": FORME_CONDENSAT,
    "HERMES_IMAGE_LINUX_ARM64": FORME_CONDENSAT, "OPENRPC_INFO_VERSION": FORME_INFO_VERSION,
    "OPENRPC_METHODES": re.compile(r"[1-9][0-9]*"), "OPENRPC_SHA256": re.compile(r"[0-9a-f]{64}"),
    "CONTRAT_ACP_POSTE": re.compile(r"acp-poste/[0-9]+"),
}

EPINGLE = "hermes/contrat/HERMES_VERSION"
DOCKERFILE = "hermes/image/Dockerfile"
OPENRPC = "hermes/contrat/gateway-contract.openrpc.json"
LICENCE = "hermes/contrat/LICENSE-hermes-agent.txt"
README_CONTRAT = "hermes/contrat/README.md"
TIERS = "hermes/THIRD_PARTY.md"
VERROU = "hermes/catalogue/catalogue.lock.json"
FIXTURE_DESKTOP = "apps/desktop/tests/fixtures/hermes/meta.json"
FIXTURE_INTERFACE = "apps/interface/tests/fixtures.ts"
GREFFON = "hermes/plugins/acp-poste/plugin.yaml"
# Épingles fortes : écrites par ``ecrire``, comparées par ``verifier``. ``requires_hermes`` (borne inférieure du
# greffon) n'en fait pas partie : elle est contrôlée, jamais réécrite.
EPINGLES_FORTES = (EPINGLE, DOCKERFILE, OPENRPC, LICENCE, README_CONTRAT, TIERS, VERROU, FIXTURE_DESKTOP,
                   FIXTURE_INTERFACE)

# Programme lancé dans l'image pour lister les skills livrées et optionnelles avec le chargeur de Hermes lui-même
# (comme hermes/tests/image/test_catalogue.py) ; Hermes détourne stdout à l'import : résultat dans un fichier.
PROGRAMME_SKILLS = (
    "import json; from pathlib import Path\n"
    "from agent.skill_utils import iter_skill_index_files, parse_frontmatter\n"
    "def noms(racine):\n"
    "    r = set()\n"
    "    for p in iter_skill_index_files(Path(racine), 'SKILL.md'):\n"
    "        fm, _ = parse_frontmatter(p.read_text(encoding='utf-8')[:4000])\n"
    "        r.add(fm.get('name', p.parent.name))\n"
    "    return sorted(r)\n"
    "json.dump({'livrees': noms('/opt/hermes/skills'), 'optionnelles': noms('/opt/hermes/optional-skills')},\n"
    "          open('/tmp/acp-skills.json', 'w', encoding='utf-8'))\n")


class Refus(Exception):
    """Refus explicite (code 2), message en français."""


@dataclass
class Resultat:
    code: int
    sortie: bytes = b""
    erreur: bytes = b""

    @property
    def texte(self) -> str:
        return self.sortie.decode("utf-8", errors="replace")


Executeur = Callable[[Sequence[str], int], Resultat]
LecteurUrl = Callable[[str], bytes]


def executer_reel(arguments: Sequence[str], delai: int) -> Resultat:
    try:
        fini = subprocess.run(list(arguments), capture_output=True, timeout=delai)
    except FileNotFoundError:
        raise Refus(f"« {arguments[0]} » introuvable sur cet hôte : installez-le (docker et git sont exigés).")
    except subprocess.TimeoutExpired:
        raise Refus(f"« {' '.join(arguments[:4])} … » n'a pas répondu en {delai} s.")
    return Resultat(fini.returncode, fini.stdout, fini.stderr)


def est_page_de_l_api(url: object) -> bool:
    """Vrai seulement pour une page de l'API publique des étiquettes de l'image, en https (la première, ou le lien
    « next » qu'elle donne : ``…/tags?name=v&page=2&page_size=100``)."""
    if not isinstance(url, str):
        return False
    morceaux = urllib.parse.urlsplit(url)
    return (morceaux.scheme, morceaux.netloc, morceaux.path) == ("https", HOTE_DOCKER_HUB, CHEMIN_API_DOCKER_HUB)


def lire_url_reel(url: str) -> bytes:
    """Lecture d'une page de l'API de Docker Hub : adresse contrôlée, délai de 60 s, au plus LIMITE_PAGE octets."""
    if not est_page_de_l_api(url):
        raise Refus(f"Adresse hors de l'API publique de Docker Hub refusée : {url!r}.")
    requete = urllib.request.Request(url, headers={"User-Agent": "acp-monter-hermes"})
    with urllib.request.urlopen(requete, timeout=60) as reponse:  # noqa: S310 (adresse contrôlée ci-dessus, https)
        brut = reponse.read(LIMITE_PAGE + 1)
    if len(brut) > LIMITE_PAGE:
        raise Refus(f"Page de l'API de Docker Hub au-delà de {LIMITE_PAGE} octets : lecture arrêtée, rien n'est conclu.")
    return brut


# =========================================================================== valeurs épinglées et relevé


@dataclass(frozen=True)
class Valeurs:
    """Valeurs d'un épinglage (lues dans HERMES_VERSION, ou relevées chez l'amont)."""

    version: str
    etiquette: str
    commit: str
    image: str
    index: str
    amd64: str
    arm64: str
    openrpc_sha256: str
    openrpc_info_version: str
    openrpc_methodes: int

    @property
    def date_de_release(self) -> str:
        return self.etiquette.removeprefix("v")


@dataclass
class Epingle:
    valeurs: Valeurs
    date: str
    contrat: str


@dataclass
class Releve:
    valeurs: Valeurs
    openrpc: bytes
    licence: bytes
    skills_livrees: Optional[List[str]] = None
    skills_optionnelles: Optional[List[str]] = None
    erreur_skills: Optional[str] = None
    journal: List[str] = field(default_factory=list)
    # Constats qui ne bloquent pas le relevé : écarts pour « verifier », avertissements pour « ecrire ».
    remarques: List[str] = field(default_factory=list)


def valider_etiquette(etiquette: str) -> str:
    if etiquette in ("latest", "main") or etiquette.startswith(("latest", "main")):
        raise Refus(f"Étiquette « {etiquette} » refusée : jamais :latest ni main, seulement une release vAAAA.M.J.")
    if not FORME_ETIQUETTE.fullmatch(etiquette):
        raise Refus(f"Étiquette « {etiquette} » hors format : attendu vAAAA.M.J ou vAAAA.M.J.N (release publiée).")
    return etiquette


def cle_etiquette(etiquette: str) -> Tuple[int, ...]:
    m = FORME_ETIQUETTE.fullmatch(etiquette)
    if m is None:
        raise Refus(f"Étiquette « {etiquette} » hors format : attendu vAAAA.M.J ou vAAAA.M.J.N.")
    return tuple(int(g or 0) for g in m.groups())


def valider_date(date: str) -> str:
    if not FORME_DATE.fullmatch(date):
        raise Refus(f"Date du relevé « {date} » hors format : attendu « J mois AAAA » en toutes lettres (par exemple "
                    "« 2 octobre 2026 »), seule forme relue par l'outil et par la concordance des épingles.")
    return date


# --------------------------------------------------------------------------- lectures : tout illisible est un refus


def _lire_octets(racine: Path, relatif: str) -> bytes:
    try:
        return (racine / relatif).read_bytes()
    except OSError as exc:
        raise Refus(f"{relatif} illisible ({type(exc).__name__}) ; rien n'est écrit.")


def _lire_texte(racine: Path, relatif: str) -> str:
    """Texte UTF-8 du fichier, fins de ligne ramenées à LF."""
    try:
        return _lire_octets(racine, relatif).decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError:
        raise Refus(f"{relatif} n'est pas en UTF-8 ; rien n'est écrit.")


def _lire_cles(texte: str) -> Dict[str, List[str]]:
    valeurs: Dict[str, List[str]] = {}
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#") and "=" in ligne:
            cle, _, valeur = ligne.partition("=")
            valeurs.setdefault(cle, []).append(valeur)
    return valeurs


def lire_epingle(racine: Path) -> Epingle:
    """Lit HERMES_VERSION et valide la forme de CHAQUE valeur avant tout usage (argument de docker ou de git, texte
    réécrit) : une valeur hors forme ou une clé en double est un refus."""
    texte = _lire_texte(racine, EPINGLE)
    lues = _lire_cles(texte)
    manquantes = [k for k in FORMES_EPINGLE if k not in lues]
    if manquantes:
        raise Refus(f"{EPINGLE} : clés absentes : {', '.join(manquantes)}.")
    doubles = [k for k in FORMES_EPINGLE if len(lues[k]) > 1]
    if doubles:
        raise Refus(f"{EPINGLE} : clés en double : {', '.join(doubles)}.")
    c = {k: lues[k][0] for k in FORMES_EPINGLE}
    hors_forme = [f"{k}={c[k]!r}" for k, forme in FORMES_EPINGLE.items() if not forme.fullmatch(c[k])]
    if hors_forme:
        raise Refus(f"{EPINGLE} : valeurs hors forme : {', '.join(hors_forme)}.")
    date = re.search(r"^# Condensats relevés le (.+) par$", texte, re.M)
    if not date:
        raise Refus(f"{EPINGLE} : ligne de date du relevé illisible.")
    return Epingle(Valeurs(c["HERMES_VERSION"], c["HERMES_TAG"], c["HERMES_COMMIT"], c["HERMES_IMAGE"],
                           c["HERMES_IMAGE_INDEX"], c["HERMES_IMAGE_LINUX_AMD64"], c["HERMES_IMAGE_LINUX_ARM64"],
                           c["OPENRPC_SHA256"], c["OPENRPC_INFO_VERSION"], int(c["OPENRPC_METHODES"])),
                   date.group(1), c["CONTRAT_ACP_POSTE"])


def _docker_dans_image(executer: Executeur, reference: str, *arguments: str, entree: str = "cat",
                       delai: int = 300) -> Resultat:
    return executer(["docker", "run", "--rm", "--network", "none", "--entrypoint", entree, reference, *arguments],
                    delai)


def decrire_openrpc(brut: bytes, origine: str) -> Tuple[str, str, int, List[str]]:
    """(SHA-256, info.version, nombre de méthodes, noms des méthodes) ; refus si le document est illisible."""
    try:
        contrat = json.loads(brut)
        info = str(contrat["info"]["version"])
        noms = [str(m["name"]) for m in contrat["methods"]]
    except (ValueError, KeyError, TypeError) as exc:
        raise Refus(f"OpenRPC de {origine} illisible ({type(exc).__name__}).")
    return hashlib.sha256(brut).hexdigest(), info, len(noms), noms


def relever(etiquette: str, executer: Executeur, image: str = IMAGE) -> Releve:
    """Relève tout ce que l'amont publie pour ``etiquette`` (réseau et Docker). Refus au premier manque."""
    valider_etiquette(etiquette)
    journal: List[str] = []

    inspect = executer(["docker", "buildx", "imagetools", "inspect", f"{image}:{etiquette}", "--format",
                        "{{json .Manifest}}"], 180)
    if inspect.code != 0:
        raise Refus(f"Condensat introuvable pour {image}:{etiquette} (docker buildx imagetools inspect, code "
                    f"{inspect.code}) : {inspect.erreur.decode('utf-8', 'replace').strip()[:300]}")
    try:
        manifeste = json.loads(inspect.sortie)
        index = manifeste["digest"]
        # Les attestations portent os « unknown » ; une variante (arm64 « v8 ») est admise ; à architecture
        # répétée, la première entrée de l'index fait foi (comme le choix de Docker au tirage).
        plates_formes: Dict[str, str] = {}
        for m in manifeste.get("manifests", []):
            plate_forme = m.get("platform") or {}
            if plate_forme.get("os") == "linux" and plate_forme.get("architecture"):
                plates_formes.setdefault(plate_forme["architecture"], m["digest"])
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise Refus(f"Manifeste de {image}:{etiquette} illisible ({type(exc).__name__}).")
    amd64, arm64 = plates_formes.get("amd64"), plates_formes.get("arm64")
    # Chaque condensat est réécrit dans HERMES_VERSION et passé à docker : forme exacte exigée, jamais « non vide ».
    if not all(isinstance(c, str) and FORME_CONDENSAT.fullmatch(c) for c in (index, amd64, arm64)):
        raise Refus(f"Condensat d'index ou de plate-forme (linux/amd64, linux/arm64) introuvable ou hors forme pour "
                    f"{image}:{etiquette}.")
    journal.append(f"index {index} ; linux/amd64 {amd64} ; linux/arm64 {arm64}")

    distant = executer(["git", "ls-remote", DEPOT_AMONT, f"refs/tags/{etiquette}", f"refs/tags/{etiquette}^{{}}"],
                       120)
    refs = dict(reversed(l.split("\t", 1)) for l in distant.texte.splitlines() if "\t" in l)
    commit = refs.get(f"refs/tags/{etiquette}^{{}}") or refs.get(f"refs/tags/{etiquette}")
    if distant.code != 0 or not commit or not FORME_COMMIT.fullmatch(commit):
        raise Refus(f"Étiquette {etiquette} introuvable dans {DEPOT_AMONT} (git ls-remote, code {distant.code}).")
    journal.append(f"commit de l'étiquette {commit}")

    reference = f"{image}@{index}"
    tire = executer(["docker", "pull", "--quiet", reference], 900)
    if tire.code != 0:
        raise Refus(f"Image {reference} non tirée (docker pull, code {tire.code}).")

    sortie_version = _docker_dans_image(executer, reference, "--version", entree=HERMES_IMAGE_BIN)
    m = SORTIE_VERSION.search(sortie_version.texte)
    if sortie_version.code != 0 or not m:
        raise Refus(f"« hermes --version » illisible dans {reference} : {sortie_version.texte.strip()[:200]!r}")
    version = m.group("version")
    journal.append(f"hermes --version : {m.group(0)}")
    if not m.group("amont") or not commit.startswith(m.group("amont")):
        raise Refus(f"Le commit de « hermes --version » ({m.group('amont') or 'absent'}) n'est pas celui de "
                    f"l'étiquette {etiquette} ({commit}).")
    if not FORME_VERSION.fullmatch(version):
        raise Refus(f"Version de Hermes « {version} » hors format X.Y.Z.")
    remarques: List[str] = []
    # Les tests de contrat tirent la date affichée de HERMES_TAG (test_contrat_image.py) : une autre convention
    # de l'amont est un écart à traiter, pas un refus.
    if m.group("date") != etiquette.removeprefix("v"):
        remarques.append(f"date de release affichée par « hermes --version » ({m.group('date')}) différente de "
                         f"l'étiquette {etiquette} (hermes/tests/contrat/test_contrat_image.py la tire de HERMES_TAG)")
    provenance = _docker_dans_image(executer, reference, CHEMIN_PROVENANCE_IMAGE)
    try:
        prov = json.loads(provenance.sortie) if provenance.code == 0 else None
    except ValueError:
        prov = None
    if not isinstance(prov, dict):
        remarques.append(f"provenance de l'image ({CHEMIN_PROVENANCE_IMAGE}) absente ou illisible (les tests de "
                         "contrat la lisent)")
    elif prov.get("revision") != commit or prov.get("version") != version:
        raise Refus(f"Provenance de l'image ({CHEMIN_PROVENANCE_IMAGE} : {prov.get('version')} / "
                    f"{prov.get('revision')}) différente de « hermes --version » et de l'étiquette ({version} / "
                    f"{commit}).")

    openrpc = _docker_dans_image(executer, reference, CHEMIN_OPENRPC_IMAGE)
    if openrpc.code != 0 or not openrpc.sortie:
        raise Refus(f"OpenRPC absent de l'image ({CHEMIN_OPENRPC_IMAGE}).")
    licence = _docker_dans_image(executer, reference, CHEMIN_LICENCE_IMAGE)
    if licence.code != 0 or not licence.sortie:
        raise Refus(f"LICENSE absent de l'image ({CHEMIN_LICENCE_IMAGE}).")
    sha, info, methodes, _ = decrire_openrpc(openrpc.sortie, reference)
    if not FORME_INFO_VERSION.fullmatch(info) or methodes < 1:
        raise Refus(f"OpenRPC de {reference} : info.version {info!r} hors forme ou aucune méthode ({methodes}) ; "
                    "rien n'est écrit.")
    journal.append(f"OpenRPC : SHA-256 {sha}, info.version {info}, {methodes} méthodes")

    releve = Releve(Valeurs(version, etiquette, commit, image, index, amd64, arm64, sha, info, methodes),
                    openrpc.sortie, licence.sortie, journal=journal, remarques=remarques)
    commande = f"cd /opt/hermes && {PYTHON_IMAGE} -c \"$0\" >/dev/null 2>&1 && cat /tmp/acp-skills.json"
    skills = _docker_dans_image(executer, reference, "-c", commande, PROGRAMME_SKILLS, entree="sh")
    try:
        noms = json.loads(skills.sortie) if skills.code == 0 else None
        releve.skills_livrees = sorted(str(n) for n in noms["livrees"])
        releve.skills_optionnelles = sorted(str(n) for n in noms["optionnelles"])
    except (ValueError, KeyError, TypeError):
        releve.erreur_skills = f"noms des skills livrées illisibles dans l'image (code {skills.code})"
    return releve


# =========================================================================== rendu des épingles fortes


class StructureInattendue(Refus):
    pass


def _remplacer(texte: str, motif: str, remplacement: Callable[[re.Match], str], fichier: str, quoi: str,
               drapeaux: int = re.M) -> str:
    resultat, nombre = re.subn(motif, remplacement, texte, flags=drapeaux)
    if nombre != 1:
        raise StructureInattendue(f"{fichier} : {quoi} trouvé {nombre} fois (une attendue) ; structure inattendue, "
                                  "rien n'est écrit.")
    return resultat


def _dans_bloc(texte: str, motif_bloc: str, champs: Sequence[Tuple[str, str]], fichier: str, nom_bloc: str) -> str:
    """Dans l'unique bloc ``motif_bloc`` (groupe 1 = contenu), pose chaque champ (motif de clé, valeur écrite)."""
    trouves = list(re.finditer(motif_bloc, texte, re.S))
    if len(trouves) != 1:
        raise StructureInattendue(f"{fichier} : bloc {nom_bloc} trouvé {len(trouves)} fois (un attendu) ; "
                                  "structure inattendue, rien n'est écrit.")
    bloc = trouves[0]
    contenu = bloc.group(1)
    for motif_cle, valeur in champs:
        cle = re.search(r"[a-z_]{3,}", motif_cle.replace("\\b", ""))
        contenu = _remplacer(contenu, motif_cle, lambda m, v=valeur: m.group(1) + v + m.group(2), fichier,
                             f"champ {nom_bloc}.{cle.group(0) if cle else motif_cle}")
    return texte[:bloc.start(1)] + contenu + texte[bloc.end(1):]


def _lf(brut: bytes) -> str:
    return brut.decode("utf-8", errors="replace").replace("\r\n", "\n")


def rendre(racine: Path, v: Valeurs, date: str, openrpc: bytes, licence: bytes) -> Dict[str, bytes]:
    """Contenu attendu de chaque épingle forte pour les valeurs ``v`` (fins de ligne LF). Seuls les champs
    épinglés changent ; tout le reste du fichier est gardé à l'octet près."""
    lire = {rel: _lire_texte(racine, rel) for rel in EPINGLES_FORTES if rel not in (OPENRPC, LICENCE)}
    sortie: Dict[str, bytes] = {}

    t = lire[EPINGLE]
    for cle, valeur in (("HERMES_VERSION", v.version), ("HERMES_TAG", v.etiquette), ("HERMES_COMMIT", v.commit),
                        ("HERMES_IMAGE", v.image), ("HERMES_IMAGE_INDEX", v.index),
                        ("HERMES_IMAGE_LINUX_AMD64", v.amd64), ("HERMES_IMAGE_LINUX_ARM64", v.arm64),
                        ("OPENRPC_INFO_VERSION", v.openrpc_info_version),
                        ("OPENRPC_METHODES", str(v.openrpc_methodes)), ("OPENRPC_SHA256", v.openrpc_sha256)):
        t = _remplacer(t, rf"^({cle}=).*()$", lambda m, x=valeur: m.group(1) + x + m.group(2), EPINGLE, cle)
    t = _remplacer(t, r"^(# Condensats relevés le ).+( par)$", lambda m: m.group(1) + date + m.group(2), EPINGLE,
                   "ligne de date du relevé")
    t = _remplacer(t, r"^(#   docker buildx imagetools inspect )\S+()$",
                   lambda m: m.group(1) + f"{v.image}:{v.etiquette}" + m.group(2), EPINGLE, "commande de relevé")
    sortie[EPINGLE] = t.encode("utf-8")

    t = lire[DOCKERFILE]
    t = _remplacer(t, r"^(FROM )\S+()$", lambda m: m.group(1) + f"{v.image}:{v.etiquette}@{v.index}" + m.group(2),
                   DOCKERFILE, "ligne FROM")
    t = _remplacer(t, r"^(# Base épinglée par le condensat de l'INDEX multi-architecture de l'étiquette )\S+()$",
                   lambda m: m.group(1) + v.etiquette + m.group(2), DOCKERFILE, "étiquette de l'en-tête")
    t = _remplacer(t, r"^(# \(Hermes Agent )\S+(, commit )[0-9a-f]+(\), relevé le ).+( par)$",
                   lambda m: m.group(1) + v.version + m.group(2) + v.commit[:7] + m.group(3) + date + m.group(4),
                   DOCKERFILE, "version, commit et date de l'en-tête")
    t = _remplacer(t, r"^(#   docker buildx imagetools inspect )\S+()$",
                   lambda m: m.group(1) + f"{v.image}:{v.etiquette}" + m.group(2), DOCKERFILE, "commande de relevé")
    sortie[DOCKERFILE] = t.encode("utf-8")

    sortie[OPENRPC] = openrpc
    sortie[LICENCE] = licence

    t = lire[README_CONTRAT]
    t = _remplacer(t, r"(de Hermes Agent, étiquette `)[^`]+(`, commit\s+`)[0-9a-f]{40}(`)",
                   lambda m: m.group(1) + v.etiquette + m.group(2) + v.commit + m.group(3), README_CONTRAT,
                   "étiquette et commit de la provenance")
    t = _remplacer(t, r"(\) le\s+)\d{1,2} \S+ \d{4}(\. SHA-256 `)[0-9a-f]{64}(`,\s+`info\.version` = `)[^`]+(`, )\d+"
                      r"( méthodes)",
                   lambda m: (m.group(1) + date + m.group(2) + v.openrpc_sha256 + m.group(3) + v.openrpc_info_version
                              + m.group(4) + str(v.openrpc_methodes) + m.group(5)),
                   README_CONTRAT, "date, SHA-256, info.version et méthodes de la provenance")
    sortie[README_CONTRAT] = t.encode("utf-8")

    t = lire[TIERS]
    t = _remplacer(t, r"(## NousResearch/hermes-agent\n(?:(?!## ).*\n)*?- Commit[  ]: `)[0-9a-f]{40}"
                      r"(` \(étiquette `)[^`]+(`\))",
                   lambda m: m.group(1) + v.commit + m.group(2) + v.etiquette + m.group(3), TIERS,
                   "commit et étiquette de la section NousResearch/hermes-agent")
    sortie[TIERS] = t.encode("utf-8")

    t = lire[VERROU]
    t = _dans_bloc(t, r'\n  "hermes": \{(.*?)\n  \}', (
        (r'("version": ")[^"]*(")', v.version), (r'("etiquette": ")[^"]*(")', v.etiquette),
        (r'("commit": ")[^"]*(")', v.commit), (r'("condensat_index": ")[^"]*(")', v.index)), VERROU, "hermes")
    t = _remplacer(t, r'("instantane_hermes": ")[^"]*(")', lambda m: m.group(1) + v.version + m.group(2), VERROU,
                   "livrees.instantane_hermes")
    sortie[VERROU] = t.encode("utf-8")

    t = lire[FIXTURE_DESKTOP]
    t = _dans_bloc(t, r'"hermes": \{([^{}]*)\}', (
        (r'("version": ")[^"]*(")', v.version), (r'("version_testee": ")[^"]*(")', v.version),
        (r'("etiquette": ")[^"]*(")', v.etiquette), (r'("commit": ")[^"]*(")', v.commit)),
        FIXTURE_DESKTOP, "hermes")
    t = _dans_bloc(t, r'"image": \{([^{}]*)\}', (
        (r'("base": ")[^"]*(")', v.image), (r'("condensat_index": ")[^"]*(")', v.index)), FIXTURE_DESKTOP, "image")
    t = _dans_bloc(t, r'"openrpc": \{([^{}]*)\}', (
        (r'("info_version": ")[^"]*(")', v.openrpc_info_version),
        (r'("info_version_epinglee": ")[^"]*(")', v.openrpc_info_version),
        (r'("methodes": )\d+()', str(v.openrpc_methodes)),
        (r'("empreinte_installee": ")[^"]*(")', v.openrpc_sha256),
        (r'("empreinte_epinglee": ")[^"]*(")', v.openrpc_sha256)), FIXTURE_DESKTOP, "openrpc")
    sortie[FIXTURE_DESKTOP] = t.encode("utf-8")

    t = lire[FIXTURE_INTERFACE]
    t = _dans_bloc(t, r"export const META = \{\n  [^\n]*\n  [^\n]*\n  hermes: \{([^{}]*)\}", (
        (r'(\bversion: ")[^"]*(")', v.version), (r'(\bversion_testee: ")[^"]*(")', v.version),
        (r'(\betiquette: ")[^"]*(")', v.etiquette), (r'(\bcommit: ")[^"]*(")', v.commit[:7])),
        FIXTURE_INTERFACE, "META.hermes")
    t = _dans_bloc(t, r"export const META = \{(?:\n  [^\n]*){3}\n  image: \{([^{}]*)\}", (
        (r'(\bbase: ")[^"]*(")', f"{v.image}:{v.etiquette}"),
        (r'(\bcondensat_index: ")[^"]*(")', v.index)), FIXTURE_INTERFACE, "META.image")
    sortie[FIXTURE_INTERFACE] = t.encode("utf-8")
    return sortie


def borne_requires_hermes(racine: Path) -> str:
    bornes = re.findall(r'^requires_hermes:\s*"?>=\s*([0-9]+\.[0-9]+\.[0-9]+)"?\s*$', _lire_texte(racine, GREFFON),
                        re.M)
    if len(bornes) != 1:
        raise StructureInattendue(f"{GREFFON} : requires_hermes absent ou hors de la forme \">=X.Y.Z\".")
    return bornes[0]


def _version_tuple(texte: str) -> Tuple[int, ...]:
    return tuple(int(p) for p in texte.split("."))


def date_du_jour(aujourd_hui: Optional[_dt.date] = None) -> str:
    jour = aujourd_hui or _dt.date.today()
    return f"{jour.day} {MOIS[jour.month - 1]} {jour.year}"


def _diff(relatif: str, avant: bytes, apres: bytes, limite: int = 12) -> List[str]:
    if relatif in (OPENRPC, LICENCE):
        return [f"    SHA-256 {hashlib.sha256(avant).hexdigest()} -> {hashlib.sha256(apres).hexdigest()}"]
    lignes = list(difflib.unified_diff(_lf(avant).splitlines(), _lf(apres).splitlines(), "dépôt", "relevé",
                                       lineterm="", n=0))
    lignes = [l for l in lignes if not l.startswith(("---", "+++", "@@"))]
    extrait = [f"    {l[:200]}" for l in lignes[:limite]]
    if len(lignes) > limite:
        extrait.append(f"    … {len(lignes) - limite} lignes de plus")
    return extrait


# =========================================================================== sous-commandes


def comparer_valeurs(epinglees: Valeurs, relevees: Valeurs) -> List[str]:
    ecarts = []
    for nom, cle in (("HERMES_VERSION", "version"), ("HERMES_TAG", "etiquette"), ("HERMES_COMMIT", "commit"),
                     ("HERMES_IMAGE", "image"), ("HERMES_IMAGE_INDEX", "index"), ("HERMES_IMAGE_LINUX_AMD64", "amd64"),
                     ("HERMES_IMAGE_LINUX_ARM64", "arm64"), ("OPENRPC_SHA256", "openrpc_sha256"),
                     ("OPENRPC_INFO_VERSION", "openrpc_info_version"), ("OPENRPC_METHODES", "openrpc_methodes")):
        a, b = getattr(epinglees, cle), getattr(relevees, cle)
        if a != b:
            ecarts.append(f"{nom} : épinglé {a}, relevé {b}")
    return ecarts


def comparer_skills(racine: Path, releve: Releve) -> List[Tuple[str, str, List[str], List[str]]]:
    """(libellé, clé du verrou, ajoutées, retirées) pour les skills livrées et optionnelles de l'image relevée face
    à ``livrees.noms`` et ``livrees.optionnelles`` du verrou du catalogue."""
    try:
        verrou = json.loads(_lire_texte(racine, VERROU))
    except ValueError as exc:
        raise Refus(f"{VERROU} : JSON illisible ({type(exc).__name__}) ; rien n'est écrit.")
    livrees = verrou.get("livrees") if isinstance(verrou, dict) else None
    if not isinstance(livrees, dict) or not all(isinstance(livrees.get(c), list) for c in ("noms", "optionnelles")):
        raise Refus(f"{VERROU} : livrees.noms et livrees.optionnelles (listes) illisibles ; rien n'est écrit.")
    resultat = []
    for libelle, cle, reels in (("livrées", "noms", releve.skills_livrees),
                                ("optionnelles", "optionnelles", releve.skills_optionnelles)):
        connues, vues = {str(n) for n in livrees[cle]}, set(reels or [])
        resultat.append((libelle, cle, sorted(vues - connues), sorted(connues - vues)))
    return resultat


def verifier(racine: Path, executer: Executeur, etiquette: Optional[str] = None,
             sortie: Callable[[str], None] = print) -> int:
    ancien = lire_epingle(racine)
    etiquette = valider_etiquette(etiquette or ancien.valeurs.etiquette)
    sortie(f"Relevé de {ancien.valeurs.image}:{etiquette} (épinglé : {ancien.valeurs.etiquette}, "
           f"Hermes {ancien.valeurs.version}).")
    releve = relever(etiquette, executer, ancien.valeurs.image)
    for ligne in releve.journal:
        sortie(f"  {ligne}")
    ecarts = comparer_valeurs(ancien.valeurs, releve.valeurs) + list(releve.remarques)

    # Répétition à blanc : chaque épingle forte rendue depuis le relevé, comparée octet pour octet. La date du
    # relevé est celle du dépôt (elle ne change qu'à une écriture qui change une valeur).
    attendu = rendre(racine, releve.valeurs, ancien.date, releve.openrpc, releve.licence)
    for relatif, contenu in attendu.items():
        actuel = _lire_octets(racine, relatif)
        if actuel != contenu:
            ecarts.append(f"{relatif} : diffère du rendu depuis le relevé")
            ecarts.extend(_diff(relatif, actuel, contenu))

    borne = borne_requires_hermes(racine)
    if _version_tuple(borne) > _version_tuple(releve.valeurs.version):
        ecarts.append(f"{GREFFON} : requires_hermes >={borne} exclut Hermes {releve.valeurs.version}")

    if releve.erreur_skills:
        ecarts.append(f"skills livrées : {releve.erreur_skills}")
    else:
        for libelle, cle, ajoutees, retirees in comparer_skills(racine, releve):
            if ajoutees or retirees:
                ecarts.append(f"skills {libelle} de l'image face à livrees.{cle} du verrou : ajoutées {ajoutees or '-'}"
                              f", retirées {retirees or '-'}")

    if ecarts:
        sortie(f"{len([e for e in ecarts if not e.startswith('    ')])} écart(s) :")
        for e in ecarts:
            sortie(e if e.startswith("    ") else f"- {e}")
        return 1
    sortie(f"Aucun écart : l'épinglage de {etiquette} est reproduit à l'octet près "
           f"({len(attendu)} épingles fortes, OpenRPC, licence, skills livrées, requires_hermes).")
    return 0


def _modifies(racine: Path, executer: Executeur, fichiers: Sequence[str]) -> List[str]:
    etat = executer(["git", "-C", str(racine), "status", "--porcelain", "--", *fichiers], 60)
    if etat.code != 0:
        raise Refus(f"git status a échoué (code {etat.code}) : {etat.erreur.decode('utf-8', 'replace')[:200]}")
    return [l[3:] for l in etat.texte.splitlines() if l.strip()]


def ecrire(racine: Path, executer: Executeur, etiquette: str, date: Optional[str] = None,
           sortie: Callable[[str], None] = print) -> int:
    valider_etiquette(etiquette)
    if date is not None:
        valider_date(date)
    modifies = _modifies(racine, executer, EPINGLES_FORTES)
    if modifies:
        raise Refus("Changements non committés dans des fichiers que l'écriture réécrirait : " + ", ".join(modifies)
                    + ". Committez-les ou annulez-les d'abord.")
    ancien = lire_epingle(racine)
    releve = relever(etiquette, executer, ancien.valeurs.image)
    for ligne in releve.journal:
        sortie(f"  {ligne}")
    openrpc_avant = _lire_octets(racine, OPENRPC)
    inchange = (releve.valeurs == ancien.valeurs and releve.openrpc == openrpc_avant
                and releve.licence == _lire_octets(racine, LICENCE))
    # La date écrite est relue par la provenance du README et par la concordance : même conservée, sa forme est exigée.
    date_ecrite = valider_date(ancien.date if inchange else (date or date_du_jour()))
    nouveau = rendre(racine, releve.valeurs, date_ecrite, releve.openrpc, releve.licence)
    ecrits = []
    for relatif, contenu in nouveau.items():
        if _lire_octets(racine, relatif) != contenu:
            (racine / relatif).write_bytes(contenu)
            ecrits.append(relatif)
    sortie(f"Épingles fortes réécrites pour {etiquette} : {', '.join(ecrits) if ecrits else 'aucun changement'}.")
    for remarque in releve.remarques:
        sortie(f"ATTENTION : {remarque}.")

    # Rapport.
    _, info_avant, _, noms_avant = decrire_openrpc(openrpc_avant, "la copie d'avant")
    _, info_apres, _, noms_apres = decrire_openrpc(releve.openrpc, "l'image relevée")
    ajoutees, retirees = sorted(set(noms_apres) - set(noms_avant)), sorted(set(noms_avant) - set(noms_apres))
    sortie(f"OpenRPC : {len(noms_avant)} -> {len(noms_apres)} méthodes ; ajoutées : {', '.join(ajoutees) or 'aucune'}"
           f" ; retirées : {', '.join(retirees) or 'aucune'}.")
    if info_avant != info_apres:
        sortie(f"ATTENTION : info.version de l'OpenRPC passe de {info_avant} à {info_apres} : la Discussion du desktop "
               "se coupe (docs/refonte/desktop.md) tant qu'il n'est pas adapté.")
    if releve.erreur_skills:
        sortie(f"Skills livrées : {releve.erreur_skills} ; à relever à la main.")
    else:
        for libelle, cle, ajout, retrait in comparer_skills(racine, releve):
            sortie(f"Skills {libelle} face à livrees.{cle} du verrou : ajoutées {', '.join(ajout) or 'aucune'} ; "
                   f"retirées {', '.join(retrait) or 'aucune'}"
                   + (" (à classer à la main : hermes/tests/image/test_catalogue.py échouera d'ici là)."
                      if ajout or retrait else "."))
    borne = borne_requires_hermes(racine)
    if _version_tuple(borne) > _version_tuple(releve.valeurs.version):
        sortie(f"ATTENTION : {GREFFON} déclare requires_hermes \">={borne}\", qui exclut Hermes "
               f"{releve.valeurs.version}. Borne NON modifiée par cet outil : à trancher à la main, jamais pour "
               "« faire passer ».")
    sortie("")
    sortie(f"Inventaire des anciennes valeurs (Hermes {ancien.valeurs.version}, {ancien.valeurs.etiquette}) :")
    afficher_inventaire(racine, executer, ancien.valeurs, sortie)
    return 0


def classer(relatif: str) -> str:
    if relatif in EPINGLES_FORTES:
        return "fortes"
    if relatif.startswith("docs/") or relatif in ("CHANGELOG.md", "README.md"):
        return "documentation"
    if re.search(r"(^|/)(tests?|fixtures)/", relatif):
        return "fixtures"
    return "citations"


GROUPES = (
    ("fortes", "Épingles fortes (réécrites par « ecrire »)"),
    ("fixtures", "Fixtures et tests (faux serveurs : à mettre à jour à la main)"),
    ("citations", "Citations dans le code et ses commentaires (à revérifier dans la PR de montée)"),
    ("documentation", "Documentation (historique : jamais réécrite)"),
)


def inventorier(racine: Path, executer: Executeur, v: Valeurs) -> Dict[str, List[str]]:
    motifs = [v.version, v.etiquette, v.commit[:7], v.index.removeprefix("sha256:")[:12]]
    arguments = ["git", "-C", str(racine), "grep", "-n", "-I", "-F"]
    for motif in motifs:
        arguments += ["-e", motif]
    trouve = executer(arguments, 120)
    if trouve.code not in (0, 1):
        raise Refus(f"git grep a échoué (code {trouve.code}).")
    groupes: Dict[str, List[str]] = {g: [] for g, _ in GROUPES}
    for ligne in trouve.texte.splitlines():
        relatif = ligne.split(":", 1)[0]
        groupes[classer(relatif)].append(ligne)
    return groupes


def afficher_inventaire(racine: Path, executer: Executeur, v: Valeurs, sortie: Callable[[str], None] = print) -> None:
    groupes = inventorier(racine, executer, v)
    for cle, titre in GROUPES:
        lignes = groupes[cle]
        fichiers = sorted({l.split(":", 1)[0] for l in lignes})
        sortie(f"{titre} : {len(lignes)} ligne(s) dans {len(fichiers)} fichier(s)")
        if cle == "documentation":
            for f in fichiers:
                sortie(f"  {f} ({sum(1 for l in lignes if l.split(':', 1)[0] == f)})")
        else:
            for l in lignes:
                sortie(f"  {l[:220]}")


def inventaire(racine: Path, executer: Executeur, sortie: Callable[[str], None] = print) -> int:
    ancien = lire_epingle(racine)
    v = ancien.valeurs
    sortie(f"Valeurs cherchées : {v.version}, {v.etiquette}, {v.commit[:7]}, {v.index.removeprefix('sha256:')[:12]}.")
    afficher_inventaire(racine, executer, v, sortie)
    return 0


def derniere(racine: Path, executer: Executeur, lire_url: LecteurUrl, sortie: Callable[[str], None] = print) -> int:
    epinglee = lire_epingle(racine).valeurs.etiquette
    distant = executer(["git", "ls-remote", "--tags", DEPOT_AMONT], 120)
    if distant.code != 0:
        raise Refus(f"git ls-remote --tags {DEPOT_AMONT} a échoué (code {distant.code}).")
    git = {l.split("\t", 1)[1].removeprefix("refs/tags/").removesuffix("^{}")
           for l in distant.texte.splitlines() if "\trefs/tags/" in l}
    hub: set = set()
    url: Optional[str] = API_DOCKER_HUB
    pages = 0
    while url and pages < 20:
        try:
            page = json.loads(lire_url(url))
            resultats = page["results"] if isinstance(page, dict) else None
            if not isinstance(resultats, list) or not all(isinstance(r, dict) for r in resultats):
                raise TypeError("page sans liste « results » d'objets")
            hub |= {str(r["name"]) for r in resultats}
            url = page.get("next")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise Refus(f"API publique de Docker Hub illisible ({type(exc).__name__}).")
        # Le lien « next » vient de la réponse : seule une page de la même API, en https, est suivie.
        if url is not None and not est_page_de_l_api(url):
            raise Refus(f"API de Docker Hub : page suivante hors de l'API publique des étiquettes refusée : {url!r}.")
        pages += 1
    if url:
        raise Refus("API de Docker Hub : plus de 20 pages d'étiquettes, liste incomplète ; rien n'est conclu.")
    releases = sorted((t for t in git & hub if FORME_ETIQUETTE.fullmatch(t)), key=cle_etiquette)
    if not releases:
        raise Refus("Aucune release vAAAA.M.J publiée à la fois en étiquette git et sur Docker Hub.")
    plus_recente = releases[-1]
    sortie(f"Dernière release publiée (git et Docker Hub) : {plus_recente}.")
    sortie(f"Release épinglée : {epinglee}.")
    seulement_git = sorted((t for t in git - hub if FORME_ETIQUETTE.fullmatch(t)), key=cle_etiquette)
    if seulement_git and cle_etiquette(seulement_git[-1]) > cle_etiquette(plus_recente):
        sortie(f"Étiquette git sans image sur Docker Hub (ignorée) : {seulement_git[-1]}.")
    if cle_etiquette(plus_recente) > cle_etiquette(epinglee):
        sortie(f"Une release plus récente existe : préparer la PR de montée (ecrire {plus_recente}).")
    else:
        sortie("Aucune release plus récente que celle épinglée.")
    return 0


def main(argv: Optional[Sequence[str]] = None, racine: Path = RACINE, executer: Executeur = executer_reel,
         lire_url: LecteurUrl = lire_url_reel) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    analyseur = argparse.ArgumentParser(prog="monter_hermes.py", description=__doc__.split("\n\n")[0])
    sous = analyseur.add_subparsers(dest="commande", required=True)
    p_verifier = sous.add_parser("verifier", help="relève et compare, sans rien écrire")
    p_verifier.add_argument("--etiquette", help="release à relever (défaut : HERMES_TAG épinglé)")
    p_ecrire = sous.add_parser("ecrire", help="réécrit les épingles fortes pour une release")
    p_ecrire.add_argument("etiquette")
    p_ecrire.add_argument("--date", help="date du relevé, en toutes lettres (défaut : aujourd'hui)")
    sous.add_parser("inventaire", help="liste les valeurs épinglées dans le dépôt")
    sous.add_parser("derniere", help="dernière release publiée (git et Docker Hub)")
    arguments = analyseur.parse_args(argv)
    try:
        if arguments.commande == "verifier":
            return verifier(racine, executer, arguments.etiquette)
        if arguments.commande == "ecrire":
            return ecrire(racine, executer, arguments.etiquette, arguments.date)
        if arguments.commande == "inventaire":
            return inventaire(racine, executer)
        return derniere(racine, executer, lire_url)
    except Refus as refus:
        print(f"Refus : {refus}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
