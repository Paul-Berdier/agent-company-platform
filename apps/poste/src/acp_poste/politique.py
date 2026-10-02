"""Politique locale du poste : lecture et validation de ``poste.toml`` (cahier P5 § 7, décision D52).

``poste.toml`` fait autorité sur le poste ; Railway ne le fournit jamais et ne peut rien y lever. Il vit sous
``%ProgramData%\\ACP\\``, en **lecture seule** pour le compte dédié ``acp-poste`` : le poste refuse de démarrer
s'il peut le modifier ou le remplacer (:func:`droits_d_ecriture`), sauf en mode ``compte = "proprietaire"``
(repli consigné, D51).

Refus en français, avec la clé et jamais la valeur d'un chemin :

- clé inconnue : « poste.toml : clé inconnue [<section>] <clé>. » ;
- type ou borne : « poste.toml : [<section>] <clé> doit être <…>. » ;
- TOML illisible : « poste.toml illisible à la ligne <n> : <raison>. ».

L'origine de Hermes est exigée en HTTPS **partout**, boucle locale comprise : ``normalize_service_origin`` admet
``http://`` sur ``127.0.0.1``, et un processus local qui y écouterait recevrait sinon le jeton machine (§ 7.3).

**Exécutant Linux (étape P6, cahier P6 § 7.2, décision D78).** Même lecteur, schéma étendu par plateforme :
``executant.toml``, versionné dans le dépôt (``executant/politique/executant.toml``) et copié par l'image en
``/etc/acp/executant.toml`` (root, 0444). Hermes ne le fournit jamais ; toute modification passe par une PR. Sections
propres à l'exécutant : ``[conditions]`` (date des décisions D83 et D84 ; sans date, la voie reste fermée),
``[disque]``, ``[git]``, et des dépôts **distants** (``[depots.<alias>] url``, clone nu sur le volume). Refus
supplémentaires : ``compte`` autre que ``uid_dedie``, origine au gabarit (``<libellé-hermes>``), URL de dépôt hors
HTTPS, hors ``[git] hotes_admis`` ou porteuse d'un identifiant, branche invalide, argv vide ; au démarrage, fichier
qui n'appartient pas à root ou inscriptible par un agent (:func:`verifier_droits`).
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import stat
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from acp_poste_contrat.inventaire import ALIAS_DEPOT, raison_identifiant
from acp_poste_contrat.machine import branche_git_valide

from .chemins import Emplacements
from .config import PosteConfigurationError, normalize_service_origin

VERSION_POLITIQUE = 1
TAILLE_MAX = 64 * 1024
VERSION_CLAUDE_MINIMALE = (2, 1, 248)
"""``--restricted`` exige Claude Code 2.1.248 (doc CC, cahier P5 § 1.3)."""

_VALEUR_POLITIQUE = re.compile(r"[a-z0-9][a-z0-9._\[\]-]{0,63}")
_VERSION = re.compile(r"(\d{1,6})\.(\d{1,6})\.(\d{1,6})")
_VERSION_TEXTE = re.compile(r"[0-9][0-9A-Za-z.+-]{0,63}")
_NOM_POSTE = re.compile(r"[^\x00-\x1f\x7f]{1,60}")
_COMPTE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,19}")
LOCALAPPDATA = "%LOCALAPPDATA%"


class PolitiqueRefusee(ValueError):
    """``poste.toml`` absent, illisible ou hors schéma : le poste ne publie rien (message français)."""


# ============================================================ modèle validé


@dataclass(frozen=True)
class SectionPoste:
    nom: str
    compte: str
    compte_attendu: str | None


@dataclass(frozen=True)
class SectionHermes:
    origine: str
    attente_max_s: int
    delai_connexion_s: int


@dataclass(frozen=True)
class SectionSondes:
    codex: bool
    claude: bool
    intervalle_s: int
    delai_sonde_s: int


@dataclass(frozen=True)
class SectionCodex:
    executable: Path
    home: Path
    version_testee: str
    modeles_permis: tuple[str, ...]
    bac_a_sable: str
    # Exécutant Linux (D79) : ce que Codex peut faire sans bubblewrap ; « refuse » : voie fermée en régime B.
    sans_bac_a_sable: str = "refuse"


@dataclass(frozen=True)
class SectionClaude:
    executable: Path
    config_dir: Path
    version_testee: str
    alias_permis: tuple[str, ...]
    ligne_etat: Path | None
    authentification: str = "abonnement"


@dataclass(frozen=True)
class SectionPolitique:
    executants: tuple[str, ...]
    efforts_interdits: tuple[str, ...]
    paliers_admis: tuple[str, ...]
    concurrence: int
    duree_max_carte_s: int
    cartes_par_jour: int
    reseau_executants: bool
    heures_agent_par_jour: int = 8


@dataclass(frozen=True)
class SectionJournal:
    niveau: str
    taille_max_mo: int
    fichiers: int


@dataclass(frozen=True)
class DepotLocal:
    alias: str
    chemin: Path
    verification: tuple[str, ...]


@dataclass(frozen=True)
class SectionDisque:
    seuil_libre_mio: int
    purge_apres_jours: int


@dataclass(frozen=True)
class SectionGit:
    auteur_nom: str
    auteur_courriel: str
    hotes_admis: tuple[str, ...]


@dataclass(frozen=True)
class DepotDistant:
    """Dépôt de l'exécutant (cahier P6 § 6.2, § 7.2) : cloné nu sur le volume depuis ``url`` (HTTPS, lecture seule)."""

    alias: str
    url: str
    branche_base: str
    acces: str
    preparation: tuple[str, ...]
    verification: tuple[str, ...]
    verification_max_s: int
    reprises_verification: int
    verification_sans_bac_a_sable: bool
    liens_symboliques: bool
    pilotage_supplementaire: tuple[str, ...]


@dataclass(frozen=True)
class Politique:
    chemin: Path
    empreinte: str
    poste: SectionPoste
    hermes: SectionHermes
    sondes: SectionSondes
    codex: SectionCodex | None
    claude: SectionClaude | None
    politique: SectionPolitique
    hermes_meme_enveloppe_que_codex: bool
    profils_interdits: tuple[Path, ...]
    journal: SectionJournal
    depots: tuple[Any, ...] = field(default_factory=tuple)
    # Étape P6 : « linux » pour executant.toml ; conditions d'usage (D83, D84), disque et git de l'exécutant.
    plateforme: str = "windows"
    conditions: dict[str, date | None] = field(default_factory=dict)
    disque: SectionDisque | None = None
    git: SectionGit | None = None

    @property
    def compte_dedie(self) -> bool:
        return self.poste.compte == "dedie"

    @property
    def nom_fichier(self) -> str:
        return "executant.toml" if self.plateforme == "linux" else "poste.toml"

    def depot(self, alias: str) -> Any:
        return next((d for d in self.depots if d.alias == alias), None)

    def resume_contrat(self) -> dict[str, Any]:
        """Bloc ``politique`` de l'inventaire (contrat ``PolitiquePoste``) ; l'exécutant ajoute les champs de P6."""
        resume = {
            "executants": list(self.politique.executants),
            "efforts_interdits": list(self.politique.efforts_interdits),
            "paliers_admis": list(self.politique.paliers_admis),
            "modeles_codex_permis": list(self.codex.modeles_permis) if self.codex else [],
            "alias_claude_permis": list(self.claude.alias_permis) if self.claude else [],
            "reseau_executants": self.politique.reseau_executants,
        }
        if self.plateforme == "linux":
            resume.update({
                "conditions": {cle: (quand.isoformat() if quand else None) for cle, quand in self.conditions.items()},
                "cartes_par_jour": self.politique.cartes_par_jour,
                "duree_max_carte_s": self.politique.duree_max_carte_s,
                "concurrence": self.politique.concurrence,
            })
        return resume


# ============================================================ lecture et validation


def _refus(section: str | None, cle: str, attendu: str) -> PolitiqueRefusee:
    lieu = f"[{section}] {cle}" if section else cle
    return PolitiqueRefusee(f"poste.toml : {lieu} doit être {attendu}.")


_RAISONS_TOML = (
    ("Invalid value", "valeur invalide"),
    ("Expected '=' after a key", "« = » attendu après la clé"),
    ("Cannot overwrite a value", "clé déjà définie"),
    ("Cannot declare", "table déclarée deux fois"),
    ("Unterminated string", "chaîne non terminée"),
    ("Invalid statement", "instruction invalide"),
    ("Invalid initial character for a key part", "nom de clé invalide"),
    ("Illegal character", "caractère interdit"),
    ("Expected newline or end of document", "fin de ligne attendue"),
)


def _raison_toml(message: str) -> tuple[str, str]:
    ligne = re.search(r"at line (\d+)", message)
    for anglais, francais in _RAISONS_TOML:
        if message.startswith(anglais):
            return (ligne.group(1) if ligne else "?"), francais
    return (ligne.group(1) if ligne else "?"), "syntaxe TOML invalide"


class _Lecteur:
    """Lit une section en refusant toute clé non consommée (« clé inconnue »)."""

    def __init__(self, section: str, donnees: Any) -> None:
        if not isinstance(donnees, dict):
            raise PolitiqueRefusee(f"poste.toml : [{section}] doit être une table.")
        self.section = section
        self.donnees = dict(donnees)
        self.vues: set[str] = set()

    def _valeur(self, cle: str, defaut: Any) -> Any:
        self.vues.add(cle)
        if cle not in self.donnees:
            if defaut is _OBLIGATOIRE:
                raise PolitiqueRefusee(f"poste.toml : [{self.section}] {cle} est obligatoire.")
            return defaut
        return self.donnees[cle]

    def entier(self, cle: str, minimum: int, maximum: int, defaut: Any = None) -> int:
        valeur = self._valeur(cle, defaut)
        if type(valeur) is not int or not minimum <= valeur <= maximum:
            if minimum == maximum:
                raise _refus(self.section, cle, f"l'entier {minimum} (seule valeur admise en v1)")
            raise _refus(self.section, cle, f"un entier entre {minimum} et {maximum}")
        return valeur

    def booleen(self, cle: str, defaut: Any = None, *, seul: bool | None = None) -> bool:
        valeur = self._valeur(cle, defaut)
        if type(valeur) is not bool:
            raise _refus(self.section, cle, "un booléen (true ou false)")
        if seul is not None and valeur is not seul:
            raise _refus(self.section, cle, f"{'true' if seul else 'false'} (seule valeur admise en v1)")
        return valeur

    def choix(self, cle: str, admis: tuple[str, ...], defaut: Any = None) -> str:
        valeur = self._valeur(cle, defaut)
        if not isinstance(valeur, str) or valeur not in admis:
            raise _refus(self.section, cle, "l'une des valeurs " + ", ".join(f"« {a} »" for a in admis))
        return valeur

    def texte(self, cle: str, motif: re.Pattern, description: str, defaut: Any = None) -> str | None:
        valeur = self._valeur(cle, defaut)
        if valeur is None and defaut is None:
            return None
        if not isinstance(valeur, str) or motif.fullmatch(valeur) is None:
            raise _refus(self.section, cle, description)
        return valeur

    def liste(self, cle: str, motif: re.Pattern, defaut: Any = None, *, maximum: int = 64) -> tuple[str, ...]:
        valeur = self._valeur(cle, defaut)
        if not isinstance(valeur, list) or len(valeur) > maximum or not all(
                isinstance(v, str) and motif.fullmatch(v) for v in valeur):
            raise _refus(self.section, cle, f"une liste d'au plus {maximum} chaînes au format {motif.pattern}")
        if len(set(valeur)) != len(valeur):
            raise _refus(self.section, cle, "une liste sans doublon")
        return tuple(valeur)

    def brut(self, cle: str, defaut: Any = None) -> Any:
        return self._valeur(cle, defaut)

    def fin(self) -> None:
        inconnues = sorted(set(self.donnees) - self.vues)
        if inconnues:
            raise PolitiqueRefusee(f"poste.toml : clé inconnue [{self.section}] {inconnues[0]}.")


_OBLIGATOIRE = object()


def _chemin(lecteur: _Lecteur, cle: str, defaut: Any, emplacements: Emplacements, *, expansion: bool = False,
            facultatif: bool = False) -> Path | None:
    valeur = lecteur.brut(cle, defaut)
    if valeur is None and facultatif:
        return None
    if isinstance(valeur, Path):
        valeur = str(valeur)
    if not isinstance(valeur, str) or not valeur or valeur != valeur.strip() or "\x00" in valeur:
        raise _refus(lecteur.section, cle, "un chemin absolu")
    if valeur.startswith(("\\\\", "//")):
        raise _refus(lecteur.section, cle, "un chemin local (chemin réseau UNC refusé)")
    if expansion and valeur[: len(LOCALAPPDATA)].upper() == LOCALAPPDATA:
        reste = valeur[len(LOCALAPPDATA):].lstrip("\\/")
        valeur = str(emplacements.localappdata / Path(*re.split(r"[\\/]+", reste))) if reste else str(
            emplacements.localappdata)
    if "%" in valeur:
        admis = " (seule %LOCALAPPDATA% est admise ici)" if expansion else " (aucune variable admise ici)"
        raise _refus(lecteur.section, cle, "un chemin absolu sans variable d'environnement" + admis)
    chemin = Path(valeur)
    if not chemin.is_absolute():
        raise _refus(lecteur.section, cle, "un chemin absolu")
    return Path(os.path.normpath(chemin))


def _fichier_si_present(section: str, cle: str, chemin: Path | None) -> Path | None:
    """« Du bon type » (cahier P5 § 7.3) : un chemin présent doit être un fichier. Son ABSENCE reste admise ici
    (le relevé dit alors « CLI absente », ou la ligne d'état « absente ») ; en mode dédié, :func:`verifier_droits`
    refuse un exécutable absent avant tout contrôle de droits."""
    if chemin is not None and chemin.exists() and not chemin.is_file():
        raise _refus(section, cle, "un fichier (le chemin désigne un dossier)")
    return chemin


def _dans(candidat: Path, racine: Path) -> bool:
    a = os.path.normcase(os.path.realpath(candidat))
    b = os.path.normcase(os.path.realpath(racine))
    return a == b or a.startswith(b.rstrip("\\/") + os.sep)


def version_numerique(texte: str | None) -> tuple[int, int, int] | None:
    trouve = _VERSION.search(texte or "")
    return tuple(int(x) for x in trouve.groups()) if trouve else None  # type: ignore[return-value]


def empreinte_du_fichier(contenu: bytes) -> str:
    """``sha256`` du fichier aux fins de ligne normalisées (LF), 12 premiers caractères (§ 7.3)."""
    return hashlib.sha256(contenu.replace(b"\r\n", b"\n")).hexdigest()[:12]


def analyser(contenu: bytes, emplacements: Emplacements, *, chemin: Path | None = None) -> Politique:
    """Valide le contenu de ``poste.toml`` ; lève :class:`PolitiqueRefusee` (français) au premier écart."""

    if len(contenu) > TAILLE_MAX:
        raise PolitiqueRefusee(f"poste.toml trop volumineux (plus de {TAILLE_MAX // 1024} Kio).")
    try:
        texte = contenu.decode("utf-8")
    except UnicodeDecodeError:
        raise PolitiqueRefusee("poste.toml illisible : encodage UTF-8 attendu.") from None
    texte = texte.removeprefix("﻿")
    try:
        donnees = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as exc:
        ligne, raison = _raison_toml(str(exc))
        raise PolitiqueRefusee(f"poste.toml illisible à la ligne {ligne} : {raison}.") from None

    sections = ("poste", "hermes", "sondes", "codex", "claude", "politique", "quotas", "isolement", "journal",
                "depots")
    for cle in donnees:
        if cle != "version" and cle not in sections:
            raise PolitiqueRefusee(f"poste.toml : clé inconnue « {cle} ».")
    if "version" not in donnees:
        raise PolitiqueRefusee("poste.toml : version est obligatoire (version = 1).")
    if type(donnees["version"]) is not int or donnees["version"] != VERSION_POLITIQUE:
        raise PolitiqueRefusee(f"poste.toml : version doit être l'entier {VERSION_POLITIQUE} (seule valeur admise).")

    p = _Lecteur("poste", donnees.get("poste", {}))
    nom = p.texte("nom", _NOM_POSTE, "un nom de 1 à 60 caractères imprimables", "Poste Windows")
    raison = raison_identifiant(nom) if nom else None
    if raison:
        # Le nom est recopié dans chaque inventaire, que la garde « aucun identifiant » refuserait : le poste
        # s'enrôlerait puis ne publierait jamais rien (relecture de P5). Jamais la valeur dans le message.
        raise PolitiqueRefusee(f"poste.toml : [poste] nom refusé ({raison}) : ce nom est publié dans chaque "
                               "inventaire, qui n'admet ni adresse, ni chemin, ni secret.")
    compte = p.choix("compte", ("dedie", "proprietaire"), "dedie")
    compte_attendu = p.texte("compte_attendu", _COMPTE, "un nom de compte Windows local (1 à 20 caractères)",
                             "acp-poste")
    p.fin()
    poste = SectionPoste(nom=nom or "Poste Windows", compte=compte,
                         compte_attendu=compte_attendu if compte == "dedie" else None)

    if "hermes" not in donnees:
        raise PolitiqueRefusee("poste.toml : la section [hermes] (origine de Hermes) est obligatoire.")
    h = _Lecteur("hermes", donnees["hermes"])
    brute = h.brut("origine", _OBLIGATOIRE)
    try:
        origine = normalize_service_origin(brute, setting="[hermes] origine") if isinstance(brute, str) else None
    except PosteConfigurationError as exc:
        raise PolitiqueRefusee(f"poste.toml : {exc}.") from None
    if origine is None or not origine.startswith("https://"):
        raise _refus("hermes", "origine", "une origine HTTPS (https://…), boucle locale comprise")
    hermes = SectionHermes(origine=origine, attente_max_s=h.entier("attente_max_s", 5, 50, 25),
                           delai_connexion_s=h.entier("delai_connexion_s", 2, 30, 10))
    h.fin()

    s = _Lecteur("sondes", donnees.get("sondes", {}))
    sondes = SectionSondes(codex=s.booleen("codex", True), claude=s.booleen("claude", True),
                           intervalle_s=s.entier("intervalle_s", 600, 86400, 1800),
                           delai_sonde_s=s.entier("delai_sonde_s", 5, 120, 30))
    s.fin()

    codex = None
    if "codex" in donnees or sondes.codex:
        if "codex" not in donnees:
            raise PolitiqueRefusee("poste.toml : [sondes] codex = true exige la section [codex].")
        c = _Lecteur("codex", donnees["codex"])
        codex = SectionCodex(
            executable=_fichier_si_present("codex", "executable", _chemin(
                c, "executable", str(emplacements.codex_par_defaut), emplacements)),
            home=_chemin(c, "home", r"%LOCALAPPDATA%\ACP\codex-home", emplacements, expansion=True),
            version_testee=c.texte("version_testee", _VERSION_TEXTE, "une version (ex. 0.156.1)", _OBLIGATOIRE),
            modeles_permis=c.liste("modeles_permis", _VALEUR_POLITIQUE, []),
            bac_a_sable=c.choix("bac_a_sable", ("elevated",), "elevated"),
        )
        c.fin()

    claude = None
    if "claude" in donnees or sondes.claude:
        if "claude" not in donnees:
            raise PolitiqueRefusee("poste.toml : [sondes] claude = true exige la section [claude].")
        c = _Lecteur("claude", donnees["claude"])
        version = c.texte("version_testee", _VERSION_TEXTE, "une version (ex. 2.1.280)", _OBLIGATOIRE)
        lue = version_numerique(version)
        if lue is None or lue < VERSION_CLAUDE_MINIMALE:
            raise _refus("claude", "version_testee", "une version de Claude Code égale ou postérieure à 2.1.248 "
                         "(--restricted)")
        claude = SectionClaude(
            executable=_fichier_si_present("claude", "executable", _chemin(
                c, "executable", str(emplacements.claude_par_defaut), emplacements)),
            config_dir=_chemin(c, "config_dir", r"%LOCALAPPDATA%\ACP\claude-config", emplacements, expansion=True),
            version_testee=version,
            alias_permis=c.liste("alias_permis", _VALEUR_POLITIQUE, ["opus", "sonnet", "haiku", "fable"]),
            ligne_etat=_fichier_si_present("claude", "ligne_etat", _chemin(c, "ligne_etat", None, emplacements,
                                                                            facultatif=True)),
        )
        c.fin()

    q = _Lecteur("politique", donnees.get("politique", {}))
    executants = q.brut("executants", ["codex", "claude"])
    if not isinstance(executants, list) or any(e not in ("codex", "claude") for e in executants) or len(
            set(executants)) != len(executants):
        raise _refus("politique", "executants", "une liste sans doublon de « codex » et « claude »")
    politique = SectionPolitique(
        executants=tuple(executants),
        efforts_interdits=q.liste("efforts_interdits", _VALEUR_POLITIQUE, ["max", "ultra", "ultracode"]),
        paliers_admis=q.liste("paliers_admis", _VALEUR_POLITIQUE, ["default"]),
        concurrence=q.entier("concurrence", 1, 1, 1),
        duree_max_carte_s=q.entier("duree_max_carte_s", 300, 14400, 3600),
        cartes_par_jour=q.entier("cartes_par_jour", 1, 200, 20),
        reseau_executants=q.booleen("reseau_executants", False, seul=False),
    )
    q.fin()

    qu = _Lecteur("quotas", donnees.get("quotas", {}))
    meme_enveloppe = qu.booleen("hermes_meme_enveloppe_que_codex", False)
    qu.fin()

    i = _Lecteur("isolement", donnees.get("isolement", {}))
    profils_bruts = i.brut("profils_interdits", [])
    if not isinstance(profils_bruts, list) or len(profils_bruts) > 16:
        raise _refus("isolement", "profils_interdits", "une liste d'au plus 16 chemins absolus")
    profils = []
    for rang, _ in enumerate(profils_bruts):
        lecteur = _Lecteur("isolement", {"profils_interdits": profils_bruts[rang]})
        profils.append(_chemin(lecteur, "profils_interdits", None, emplacements))
    i.fin()

    j = _Lecteur("journal", donnees.get("journal", {}))
    journal = SectionJournal(niveau=j.choix("niveau", ("info", "detail"), "info"),
                             taille_max_mo=j.entier("taille_max_mo", 1, 10, 1),
                             fichiers=j.entier("fichiers", 1, 20, 5))
    j.fin()

    depots_bruts = donnees.get("depots", {})
    if not isinstance(depots_bruts, dict) or len(depots_bruts) > 100:
        raise PolitiqueRefusee("poste.toml : [depots] doit compter au plus 100 dépôts ([depots.<alias>]).")
    depots = []
    for alias, table in depots_bruts.items():
        if not isinstance(alias, str) or ALIAS_DEPOT.fullmatch(alias) is None:
            raise PolitiqueRefusee("poste.toml : alias de dépôt refusé [depots.<alias>] : format "
                                   "^[a-z0-9][a-z0-9-]{0,31}$ attendu.")
        d = _Lecteur(f"depots.{alias}", table)
        chemin = _chemin(d, "chemin", _OBLIGATOIRE, emplacements)
        verification = d.brut("verification", [])
        if not isinstance(verification, list) or len(verification) > 32 or not all(
                isinstance(a, str) and a and "\x00" not in a for a in verification):
            raise _refus(f"depots.{alias}", "verification", "une liste d'arguments (argv, jamais une chaîne shell)")
        d.fin()
        if not chemin.is_dir():
            raise PolitiqueRefusee(f"poste.toml : [depots.{alias}] chemin doit désigner un dossier existant.")
        if not (chemin / ".git").exists():
            raise PolitiqueRefusee(f"poste.toml : [depots.{alias}] chemin doit désigner un dépôt git (.git absent).")
        depots.append(DepotLocal(alias=alias, chemin=chemin, verification=tuple(verification)))

    # Racines disjointes : dépôts entre eux, et des profils des CLI et du dossier du poste (executors.py:222-250).
    reserves = [("[codex] home", codex.home)] if codex else []
    if claude:
        reserves.append(("[claude] config_dir", claude.config_dir))
    reserves.append(("le dossier du poste (%LOCALAPPDATA%\\ACP)", emplacements.acp_local))
    for rang, gauche in enumerate(depots):
        for droite in depots[rang + 1:]:
            if _dans(gauche.chemin, droite.chemin) or _dans(droite.chemin, gauche.chemin):
                raise PolitiqueRefusee(f"poste.toml : les dépôts [depots.{gauche.alias}] et [depots.{droite.alias}] "
                                       "se chevauchent.")
        for nom_reserve, reserve in reserves:
            if _dans(gauche.chemin, reserve) or _dans(reserve, gauche.chemin):
                raise PolitiqueRefusee(f"poste.toml : le dépôt [depots.{gauche.alias}] chevauche {nom_reserve}.")
        for section, executable in (("codex", codex.executable if codex else None),
                                    ("claude", claude.executable if claude else None)):
            if executable is not None and _dans(executable, gauche.chemin):
                raise PolitiqueRefusee(f"poste.toml : [{section}] executable ne peut pas se trouver dans le dépôt "
                                       f"[depots.{gauche.alias}].")

    return Politique(chemin=chemin_fichier(emplacements, chemin), empreinte=empreinte_du_fichier(contenu),
                     poste=poste, hermes=hermes, sondes=sondes, codex=codex, claude=claude, politique=politique,
                     hermes_meme_enveloppe_que_codex=meme_enveloppe, profils_interdits=tuple(profils),
                     journal=journal, depots=tuple(depots))


def chemin_fichier(emplacements: Emplacements, chemin: Path | None = None) -> Path:
    return chemin if chemin is not None else emplacements.politique


def _plateforme_des(emplacements: Any) -> str:
    return getattr(emplacements, "plateforme", "windows")


def charger(emplacements: Emplacements, *, chemin: Path | None = None) -> Politique:
    """Lit et valide ``poste.toml`` (Windows) ou ``executant.toml`` (Linux), selon les emplacements de la plateforme
    (sans vérifier ses droits : :func:`verifier_droits`)."""

    fichier = chemin_fichier(emplacements, chemin)
    linux = _plateforme_des(emplacements) == "linux"
    try:
        with fichier.open("rb") as flux:
            contenu = flux.read(TAILLE_MAX + 1)
    except FileNotFoundError:
        if linux:
            raise PolitiqueRefusee("executant.toml absent : l'image de l'exécutant le copie en /etc/acp "
                                   "(executant/Dockerfile) ; refus de démarrer.") from None
        raise PolitiqueRefusee("poste.toml absent : l'installeur du poste le crée sous %ProgramData%\\ACP "
                               "(packaging/poste/Installer-PosteAcp.ps1).") from None
    except OSError:
        raise PolitiqueRefusee(("executant.toml illisible par le superviseur." if linux else
                                "poste.toml illisible par le compte du poste.")) from None
    if linux:
        return analyser_executant(contenu, emplacements, chemin=fichier)
    return analyser(contenu, emplacements, chemin=fichier)


# ============================================================ executant.toml (Linux, cahier P6 § 7.2)

SECTIONS_EXECUTANT = ("poste", "hermes", "conditions", "sondes", "codex", "claude", "politique", "quotas", "disque",
                      "git", "journal", "depots")
_HOTE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")
_AUTEUR = re.compile(r"([^<>\x00-\x1f\x7f]{1,60}?) <([A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190})>")
_ARGUMENT = re.compile(r"[^\x00]{1,4096}")
_PILOTAGE_SUPPLEMENTAIRE = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._/ -]{0,199}")
GABARIT = ("[hermes] origine vaut encore le gabarit (<libellé-hermes>) : remplacez-le par le libellé du sous-domaine "
           "choisi dans .railway/railway.ts, par une PR (CI verte) ; refus de démarrer.")


def _chemin_posix(lecteur: _Lecteur, cle: str, defaut: Any) -> Path:
    """Chemin ABSOLU de l'exécutant (forme POSIX, sans variable ni « .. »), validé quelle que soit la plateforme des
    tests."""
    valeur = lecteur.brut(cle, defaut)
    if not isinstance(valeur, str) or not valeur.startswith("/") or "\\" in valeur or "%" in valeur \
            or "\x00" in valeur or valeur != valeur.strip():
        raise _refus(lecteur.section, cle, "un chemin absolu POSIX (/…), sans variable")
    if ".." in valeur.split("/"):
        raise _refus(lecteur.section, cle, "un chemin absolu sans « .. »")
    return Path(posixpath.normpath(valeur))


def _argv(lecteur: _Lecteur, cle: str, defaut: Any, *, obligatoire: bool) -> tuple[str, ...]:
    valeur = lecteur.brut(cle, defaut)
    if not isinstance(valeur, list) or len(valeur) > 64 or not all(
            isinstance(a, str) and _ARGUMENT.fullmatch(a) for a in valeur):
        raise _refus(lecteur.section, cle, "une liste d'arguments (argv, jamais une chaîne shell)")
    if obligatoire and not valeur:
        raise _refus(lecteur.section, cle, "un argv non vide")
    return tuple(valeur)


def _date_de_decision(lecteur: _Lecteur, cle: str) -> date | None:
    valeur = lecteur.brut(cle, "")
    if valeur == "":
        return None
    if isinstance(valeur, date):
        return valeur
    if isinstance(valeur, str):
        try:
            return date.fromisoformat(valeur)
        except ValueError:
            pass
    raise _refus(lecteur.section, cle, "une date AAAA-MM-JJ (décision consignée) ou \"\" (non décidé : voie fermée)")


def _url_depot(lecteur: _Lecteur, hotes_admis: tuple[str, ...]) -> str:
    valeur = lecteur.brut("url", _OBLIGATOIRE)
    if not isinstance(valeur, str) or valeur != valeur.strip() or len(valeur) > 300:
        raise _refus(lecteur.section, "url", "une URL https://")
    if "<" in valeur or ">" in valeur:
        raise PolitiqueRefusee(f"executant.toml : [{lecteur.section}] url vaut encore un gabarit : remplacez-le par "
                               "l'URL HTTPS du dépôt, par une PR.")
    if "@" in valeur:
        raise _refus(lecteur.section, "url", "une URL sans identifiant (« @ » refusé : le jeton de lecture passe par "
                     "GIT_ASKPASS, jamais par l'URL)")
    try:
        decoupe = urlsplit(valeur)
        port = decoupe.port
    except ValueError:
        raise _refus(lecteur.section, "url", "une URL https:// lisible") from None
    if decoupe.scheme != "https" or not decoupe.hostname or decoupe.query or decoupe.fragment or port not in (
            None, 443):
        raise _refus(lecteur.section, "url", "une URL https:// sans port, requête ni fragment")
    if decoupe.hostname not in hotes_admis:
        raise _refus(lecteur.section, "url", "une URL sur un hôte de [git] hotes_admis")
    if not re.fullmatch(r"/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+?(?:\.git)?", decoupe.path or ""):
        raise _refus(lecteur.section, "url", "une URL de dépôt de la forme https://<hôte>/<propriétaire>/<dépôt>")
    return valeur


def analyser_executant(contenu: bytes, emplacements: Any, *, chemin: Path | None = None) -> Politique:
    """Valide ``executant.toml`` ; lève :class:`PolitiqueRefusee` (français, « executant.toml : … ») au premier écart."""
    try:
        return _analyser_executant(contenu, emplacements, chemin=chemin)
    except PolitiqueRefusee as exc:
        # Les lecteurs communs nomment « poste.toml » : l'exécutant lit executant.toml.
        raise PolitiqueRefusee(str(exc).replace("poste.toml", "executant.toml")) from None


def _analyser_executant(contenu: bytes, emplacements: Any, *, chemin: Path | None) -> Politique:
    if len(contenu) > TAILLE_MAX:
        raise PolitiqueRefusee(f"poste.toml trop volumineux (plus de {TAILLE_MAX // 1024} Kio).")
    try:
        texte = contenu.decode("utf-8").removeprefix("﻿")
    except UnicodeDecodeError:
        raise PolitiqueRefusee("poste.toml illisible : encodage UTF-8 attendu.") from None
    try:
        donnees = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as exc:
        ligne, raison = _raison_toml(str(exc))
        raise PolitiqueRefusee(f"poste.toml illisible à la ligne {ligne} : {raison}.") from None
    for cle in donnees:
        if cle != "version" and cle not in SECTIONS_EXECUTANT:
            raise PolitiqueRefusee(f"poste.toml : clé inconnue « {cle} ».")
    if type(donnees.get("version")) is not int or donnees["version"] != VERSION_POLITIQUE:
        raise PolitiqueRefusee(f"poste.toml : version doit être l'entier {VERSION_POLITIQUE} (seule valeur admise).")

    p = _Lecteur("poste", donnees.get("poste", {}))
    nom = p.texte("nom", _NOM_POSTE, "un nom de 1 à 60 caractères imprimables", "Exécutant Railway")
    raison = raison_identifiant(nom) if nom else None
    if raison:
        raise PolitiqueRefusee(f"poste.toml : [poste] nom refusé ({raison}) : ce nom est publié dans chaque "
                               "inventaire, qui n'admet ni adresse, ni chemin, ni secret.")
    compte = p.brut("compte", "uid_dedie")
    if compte != "uid_dedie":
        raise PolitiqueRefusee("poste.toml : [poste] compte doit être « uid_dedie » sous Linux (un UID par agent) : "
                               "« dedie » et « proprietaire » sont des modes du poste Windows.")
    p.fin()
    poste = SectionPoste(nom=nom or "Exécutant Railway", compte="uid_dedie", compte_attendu=None)

    if "hermes" not in donnees:
        raise PolitiqueRefusee("poste.toml : la section [hermes] (origine de Hermes) est obligatoire.")
    h = _Lecteur("hermes", donnees["hermes"])
    brute = h.brut("origine", _OBLIGATOIRE)
    if isinstance(brute, str) and ("<" in brute or ">" in brute):
        raise PolitiqueRefusee("poste.toml : " + GABARIT)
    try:
        origine = normalize_service_origin(brute, setting="[hermes] origine") if isinstance(brute, str) else None
    except PosteConfigurationError as exc:
        raise PolitiqueRefusee(f"poste.toml : {exc}.") from None
    if origine is None or not origine.startswith("https://"):
        raise _refus("hermes", "origine", "une origine HTTPS (https://…)")
    hermes = SectionHermes(origine=origine, attente_max_s=h.entier("attente_max_s", 5, 50, 25),
                           delai_connexion_s=h.entier("delai_connexion_s", 2, 30, 10))
    h.fin()

    c = _Lecteur("conditions", donnees.get("conditions", {}))
    conditions = {"codex": _date_de_decision(c, "codex_decide_le"),
                  "claude": _date_de_decision(c, "claude_decide_le")}
    c.fin()

    s = _Lecteur("sondes", donnees.get("sondes", {}))
    sondes = SectionSondes(codex=s.booleen("codex", True), claude=s.booleen("claude", True),
                           intervalle_s=s.entier("intervalle_s", 600, 86400, 1800),
                           delai_sonde_s=s.entier("delai_sonde_s", 5, 120, 30))
    s.fin()

    codex = None
    if "codex" in donnees or sondes.codex:
        if "codex" not in donnees:
            raise PolitiqueRefusee("poste.toml : [sondes] codex = true exige la section [codex].")
        x = _Lecteur("codex", donnees["codex"])
        codex = SectionCodex(
            executable=_fichier_si_present("codex", "executable", _chemin_posix(
                x, "executable", emplacements.codex_par_defaut.as_posix())),
            home=_chemin_posix(x, "home", "/donnees/codex"),
            version_testee=x.texte("version_testee", _VERSION_TEXTE, "une version (ex. 0.156.1)", _OBLIGATOIRE),
            modeles_permis=x.liste("modeles_permis", _VALEUR_POLITIQUE, []),
            bac_a_sable="bubblewrap",
            sans_bac_a_sable=x.choix("sans_bac_a_sable", ("refuse", "edition_seule", "acces_complet"), "refuse"),
        )
        x.fin()
        if codex.sans_bac_a_sable != "refuse":
            # Options (a) et (b) de D79 : (b) n'est prouvée par aucun essai, (a) exige une acceptation écrite ; ni
            # l'une ni l'autre n'est mise en œuvre en P6 : refus plutôt qu'un réglage qui ferait semblant.
            raise PolitiqueRefusee(f"poste.toml : [codex] sans_bac_a_sable = « {codex.sans_bac_a_sable} » : option "
                                   "de D79 non prise en charge en P6 (seule « refuse » l'est) ; refus de démarrer.")

    claude = None
    if "claude" in donnees or sondes.claude:
        if "claude" not in donnees:
            raise PolitiqueRefusee("poste.toml : [sondes] claude = true exige la section [claude].")
        y = _Lecteur("claude", donnees["claude"])
        version = y.texte("version_testee", _VERSION_TEXTE, "une version (ex. 2.1.283)", _OBLIGATOIRE)
        lue = version_numerique(version)
        if lue is None or lue < VERSION_CLAUDE_MINIMALE:
            raise _refus("claude", "version_testee", "une version de Claude Code égale ou postérieure à 2.1.248 "
                         "(--restricted)")
        authentification = y.choix("authentification", ("abonnement", "cle_api"), "abonnement")
        if authentification == "cle_api":
            raise PolitiqueRefusee("poste.toml : [claude] authentification = « cle_api » : bascule prévue (D84) mais "
                                   "non prise en charge en P6 ; refus plutôt qu'un réglage qui ferait semblant.")
        claude = SectionClaude(
            executable=_fichier_si_present("claude", "executable", _chemin_posix(
                y, "executable", emplacements.claude_par_defaut.as_posix())),
            config_dir=_chemin_posix(y, "config_dir", "/donnees/claude"),
            version_testee=version,
            alias_permis=y.liste("alias_permis", _VALEUR_POLITIQUE, ["opus", "sonnet"]),
            ligne_etat=None, authentification=authentification,
        )
        y.fin()

    q = _Lecteur("politique", donnees.get("politique", {}))
    executants = q.brut("executants", ["codex", "claude"])
    if not isinstance(executants, list) or any(e not in ("codex", "claude") for e in executants) or len(
            set(executants)) != len(executants):
        raise _refus("politique", "executants", "une liste sans doublon de « codex » et « claude »")
    politique = SectionPolitique(
        executants=tuple(executants),
        efforts_interdits=q.liste("efforts_interdits", _VALEUR_POLITIQUE, ["max", "ultra", "ultracode"]),
        paliers_admis=q.liste("paliers_admis", _VALEUR_POLITIQUE, ["default"]),
        concurrence=q.entier("concurrence", 1, 1, 1),
        duree_max_carte_s=q.entier("duree_max_carte_s", 300, 14400, 3600),
        cartes_par_jour=q.entier("cartes_par_jour", 1, 200, 20),
        reseau_executants=q.booleen("reseau_executants", False, seul=False),
        heures_agent_par_jour=q.entier("heures_agent_par_jour", 1, 24, 8),
    )
    q.fin()

    qu = _Lecteur("quotas", donnees.get("quotas", {}))
    meme_enveloppe = qu.booleen("hermes_meme_enveloppe_que_codex", False)
    qu.fin()

    d = _Lecteur("disque", donnees.get("disque", {}))
    disque = SectionDisque(seuil_libre_mio=d.entier("seuil_libre_mio", 256, 1_000_000, 1024),
                           purge_apres_jours=d.entier("purge_apres_jours", 1, 90, 7))
    d.fin()

    g = _Lecteur("git", donnees.get("git", {}))
    auteur = g.brut("auteur", "ACP exécutant <executant@acp.invalid>")
    trouve = _AUTEUR.fullmatch(auteur) if isinstance(auteur, str) else None
    if trouve is None:
        raise _refus("git", "auteur", "« Nom <courriel> »")
    hotes = g.liste("hotes_admis", _HOTE, ["github.com"], maximum=8)
    if not hotes:
        raise _refus("git", "hotes_admis", "une liste non vide de noms d'hôte")
    g.fin()
    git = SectionGit(auteur_nom=trouve.group(1), auteur_courriel=trouve.group(2), hotes_admis=hotes)

    j = _Lecteur("journal", donnees.get("journal", {}))
    journal = SectionJournal(niveau=j.choix("niveau", ("info", "detail"), "info"),
                             taille_max_mo=j.entier("taille_max_mo", 1, 10, 1),
                             fichiers=j.entier("fichiers", 1, 20, 5))
    j.fin()

    depots_bruts = donnees.get("depots", {})
    if not isinstance(depots_bruts, dict) or len(depots_bruts) > 100:
        raise PolitiqueRefusee("poste.toml : [depots] doit compter au plus 100 dépôts ([depots.<alias>]).")
    depots = []
    for alias, table in depots_bruts.items():
        if not isinstance(alias, str) or ALIAS_DEPOT.fullmatch(alias) is None:
            raise PolitiqueRefusee("poste.toml : alias de dépôt refusé [depots.<alias>] : format "
                                   "^[a-z0-9][a-z0-9-]{0,31}$ attendu.")
        r = _Lecteur(f"depots.{alias}", table)
        url = _url_depot(r, git.hotes_admis)
        branche = r.brut("branche_base", "main")
        if not isinstance(branche, str) or not branche_git_valide(branche):
            raise _refus(f"depots.{alias}", "branche_base", "un nom de branche git valide")
        supplement = r.liste("pilotage_supplementaire", _PILOTAGE_SUPPLEMENTAIRE, [], maximum=32)
        if any(".." in chemin_relatif.split("/") for chemin_relatif in supplement):
            raise _refus(f"depots.{alias}", "pilotage_supplementaire", "des chemins relatifs au dépôt, sans « .. »")
        depots.append(DepotDistant(
            alias=alias, url=url, branche_base=branche,
            acces=r.choix("acces", ("public", "jeton_lecture"), "jeton_lecture"),
            preparation=_argv(r, "preparation", [], obligatoire=False),
            verification=_argv(r, "verification", _OBLIGATOIRE, obligatoire=True),
            verification_max_s=r.entier("verification_max_s", 30, 7200, 900),
            reprises_verification=r.entier("reprises_verification", 0, 5, 2),
            verification_sans_bac_a_sable=r.booleen("verification_sans_bac_a_sable", False),
            liens_symboliques=r.booleen("liens_symboliques", False),
            pilotage_supplementaire=supplement,
        ))
        r.fin()
    urls = [depot.url.rstrip("/").removesuffix(".git").lower() for depot in depots]
    if len(set(urls)) != len(urls):
        raise PolitiqueRefusee("poste.toml : deux dépôts [depots.<alias>] désignent la même URL.")

    return Politique(chemin=chemin_fichier(emplacements, chemin), empreinte=empreinte_du_fichier(contenu),
                     poste=poste, hermes=hermes, sondes=sondes, codex=codex, claude=claude, politique=politique,
                     hermes_meme_enveloppe_que_codex=meme_enveloppe, profils_interdits=(), journal=journal,
                     depots=tuple(depots), plateforme="linux", conditions=conditions, disque=disque, git=git)


# ============================================================ droits (Windows)

GENERIC_WRITE = 0x40000000
DELETE = 0x00010000
WRITE_DAC = 0x00040000
WRITE_OWNER = 0x00080000
FILE_ADD_FILE = 0x00000002
FILE_ADD_SUBDIRECTORY = 0x00000004
_ERREUR_ACCES_REFUSE = 5

DROITS_FICHIER = (("GENERIC_WRITE", GENERIC_WRITE), ("DELETE", DELETE), ("WRITE_DAC", WRITE_DAC),
                  ("WRITE_OWNER", WRITE_OWNER))
DROITS_DOSSIER = (("FILE_ADD_FILE", FILE_ADD_FILE), ("DELETE", DELETE), ("WRITE_DAC", WRITE_DAC),
                  ("WRITE_OWNER", WRITE_OWNER))
# Un dossier examiné pour lui-même (bibliothèques de l'interpréteur et du poste) : y créer un sous-dossier suffit à y
# planter un paquet (``sitecustomize/``) ; ``FILE_ADD_FILE`` suffit pour un ``.pth`` ou un module.
DROITS_DOSSIER_SEUL = (("FILE_ADD_FILE", FILE_ADD_FILE), ("FILE_ADD_SUBDIRECTORY", FILE_ADD_SUBDIRECTORY),
                       ("DELETE", DELETE), ("WRITE_DAC", WRITE_DAC), ("WRITE_OWNER", WRITE_OWNER))


def _ouverture_windows(chemin: Path, acces: int, dossier: bool) -> str:
    """« ouvert », « refuse » ou « indetermine » : ``CreateFileW`` avec ce seul droit, sans rien écrire."""

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    invalide = wintypes.HANDLE(-1).value
    # Partage complet (un lecteur ne fausse pas le test) ; OPEN_EXISTING (rien n'est créé ni tronqué) ;
    # FILE_FLAG_BACKUP_SEMANTICS seulement pour ouvrir un dossier (sans privilège de sauvegarde activé, il ne
    # contourne aucune ACL).
    poignee = kernel32.CreateFileW(str(chemin), acces, 0x7, None, 3, 0x02000000 if dossier else 0, None)
    if poignee not in (None, invalide):
        kernel32.CloseHandle(poignee)
        return "ouvert"
    return "refuse" if ctypes.get_last_error() == _ERREUR_ACCES_REFUSE else "indetermine"


_ouverture: Callable[[Path, int, bool], str] = _ouverture_windows


def droits_d_ecriture(fichier: Path) -> list[str]:
    """Droits par lesquels le compte courant pourrait modifier ou remplacer ``fichier`` (cahier P5 § 7.1) :
    ``GENERIC_WRITE``, ``DELETE``, ``WRITE_DAC``, ``WRITE_OWNER`` sur le fichier, puis ``FILE_ADD_FILE``,
    ``DELETE``, ``WRITE_DAC`` et ``WRITE_OWNER`` sur son dossier. Une ouverture réussie, un partage refusé ou une
    erreur autre que « accès refusé » comptent (« indéterminé » refuse aussi). Liste vide : non modifiable."""

    obtenus = []
    cibles = [(fichier, DROITS_FICHIER, False)] if fichier.exists() else []
    cibles.append((fichier.parent, DROITS_DOSSIER, True))
    for cible, droits, dossier in cibles:
        for nom, acces in droits:
            issue = _ouverture(cible, acces, dossier)
            if issue != "refuse":
                quoi = "dossier" if dossier else "fichier"
                obtenus.append(f"{nom} ({quoi}{', indéterminé' if issue == 'indetermine' else ''})")
    return obtenus


def droits_d_ecriture_dossier(dossier: Path) -> list[str]:
    """Droits par lesquels le compte courant pourrait ajouter, remplacer ou réautoriser quoi que ce soit DANS
    ``dossier`` (examiné pour lui-même, pas par son parent). Mêmes règles que :func:`droits_d_ecriture`."""

    obtenus = []
    for nom, acces in DROITS_DOSSIER_SEUL:
        issue = _ouverture(dossier, acces, True)
        if issue != "refuse":
            obtenus.append(f"{nom} (dossier{', indéterminé' if issue == 'indetermine' else ''})")
    return obtenus


def compte_courant() -> str:
    """Nom du compte du jeton du processus (``GetUserNameW``), jamais la variable ``USERNAME``."""

    if os.name != "nt":
        import getpass

        return getpass.getuser()
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.GetUserNameW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    advapi32.GetUserNameW.restype = wintypes.BOOL
    taille = wintypes.DWORD(257)
    tampon = ctypes.create_unicode_buffer(taille.value)
    if not advapi32.GetUserNameW(tampon, ctypes.byref(taille)):
        raise PolitiqueRefusee("Nom du compte Windows courant illisible.")
    return tampon.value


def verifier_compte(politique: Politique, courant: str) -> None:
    """Mode ``dedie`` : le poste tourne sous ``compte_attendu`` (casse indifférente), sinon refus (code 2). Exécutant
    Linux : le superviseur tourne en root (il change d'UID pour chaque agent) ; vérifié par :func:`verifier_droits`."""

    if politique.plateforme == "linux":
        return
    if politique.compte_dedie and courant.casefold() != (politique.poste.compte_attendu or "").casefold():
        raise PolitiqueRefusee(f"Compte Windows refusé : le poste doit tourner sous « {politique.poste.compte_attendu} » "
                               "(poste.toml, [poste] compte_attendu) ; lancez-le par sa tâche planifiée ou par "
                               "« runas /user:acp-poste ».")


def _modifiable_par_un_agent(chemin: Path, proprietaire: int) -> str | None:
    """Raison pour laquelle un agent (UID 10001 à 10003, groupe 10100) pourrait modifier ou remplacer ``chemin``, ou
    ``None`` : propriétaire autre que ``proprietaire`` (root en production), écriture du groupe ou des autres, lien
    symbolique."""
    try:
        etat = os.lstat(chemin)
    except OSError:
        return "illisible"
    if stat.S_ISLNK(etat.st_mode):
        return "lien symbolique"
    if etat.st_uid != proprietaire:
        return "autre propriétaire que root"
    if etat.st_mode & 0o022:
        return "inscriptible par le groupe ou les autres"
    return None


def _verifier_droits_linux(politique: Politique, proprietaire: int) -> None:
    raison = _modifiable_par_un_agent(politique.chemin, proprietaire)
    for cible in (politique.chemin.parent,) if raison is None else ():
        raison = _modifiable_par_un_agent(cible, proprietaire)
    if raison:
        raise PolitiqueRefusee(f"executant.toml modifiable ou remplaçable par un agent ({raison}) : refus de "
                               "démarrer (attendu : root, 0444, dossier root non inscriptible ; D78).")
    for section, executable in (("codex", politique.codex.executable if politique.codex else None),
                                ("claude", politique.claude.executable if politique.claude else None)):
        if executable is None:
            continue
        if not executable.is_file():
            raise PolitiqueRefusee(f"[{section}] executable : fichier introuvable dans l'image : refus de démarrer "
                                   "(décisions D54 et D70).")
        for cible in (executable, executable.parent):
            raison = _modifiable_par_un_agent(cible, proprietaire)
            if raison:
                raise PolitiqueRefusee(f"[{section}] executable : binaire de la CLI modifiable par un agent ({raison}) "
                                       ": refus de démarrer (décision D54).")


def verifier_droits(politique: Politique, *, proprietaire: int = 0) -> None:
    """Mode ``dedie`` : refus si le compte du poste peut modifier ou remplacer ``poste.toml`` ou un exécutable des
    CLI (et ``codex-windows-sandbox-setup.exe``) ; en mode ``proprietaire``, rien n'est vérifié (D51).

    Exécutant Linux : ``executant.toml``, son dossier, les binaires des CLI et leur dossier doivent appartenir à root
    (``proprietaire``, injecté par les tests sans root) et n'être inscriptibles ni par le groupe ni par les autres."""

    if politique.plateforme == "linux":
        _verifier_droits_linux(politique, proprietaire)
        return
    if not politique.compte_dedie:
        return
    obtenus = droits_d_ecriture(politique.chemin)
    if obtenus:
        raise PolitiqueRefusee("poste.toml est modifiable ou remplaçable par le compte du poste ("
                               + ", ".join(obtenus[:3]) + ") : refus de démarrer. Rétablissez ses droits "
                               "(Administrateurs et SYSTEM seuls en écriture, le poste en lecture).")
    for section, executable in (("codex", politique.codex.executable if politique.codex else None),
                                ("claude", politique.claude.executable if politique.claude else None)):
        if executable is None:
            continue
        cibles = [executable]
        if section == "codex":
            cibles.append(executable.parent.parent / "codex-resources" / "codex-windows-sandbox-setup.exe")
            cibles.append(executable.parent / "codex-windows-sandbox-setup.exe")
        if not executable.is_file():
            # Sans ce contrôle, le dossier absent donnait « indéterminé », donc « modifiable » : message trompeur
            # (relecture de P5). Aucun chemin dans le message (le diagnostic le recopie).
            raise PolitiqueRefusee(f"[{section}] executable : fichier introuvable ; réinstallez la CLI "
                                   "(Installer-PosteAcp.ps1, étape 5) ou corrigez poste.toml : refus de démarrer "
                                   "(décisions D54 et D70).")
        for cible in cibles:
            if not cible.exists() and cible != executable:
                continue
            obtenus = droits_d_ecriture(cible)
            if obtenus:
                raise PolitiqueRefusee(f"[{section}] executable : un binaire de la CLI est modifiable par le compte du "
                                       f"poste ({', '.join(obtenus[:3])}) : refus de démarrer (décision D54).")


def cibles_de_l_interpreteur() -> list[tuple[str, Path, bool]]:
    """(libellé, chemin, dossier ?) de ce que ``python -I lancer.py`` exécute ou importe : l'interpréteur et ses
    bibliothèques, ``site-packages`` et ses ``.pth`` (``-I`` ne retire QUE ``PYTHONPATH``, le site utilisateur et le
    dossier courant : les ``.pth`` de l'interpréteur s'exécutent toujours), puis les bibliothèques du poste, dossier
    par dossier. Les fichiers de la bibliothèque standard ne sont pas examinés un à un : ils héritent des droits de
    leur dossier (limite dite, relecture de P5)."""

    import sys
    import sysconfig

    vues: set[str] = set()
    cibles: list[tuple[str, Path, bool]] = []

    def ajouter(libelle: str, chemin: Path, dossier: bool) -> None:
        cle = os.path.normcase(os.path.abspath(chemin))
        if cle not in vues and chemin.exists():
            vues.add(cle)
            cibles.append((libelle, chemin, dossier))

    for prefixe in (Path(sys.base_prefix), Path(sys.prefix)):
        ajouter("dossier de l'interpréteur Python", prefixe, True)
        ajouter("DLLs de l'interpréteur", prefixe / "DLLs", True)
        if prefixe.is_dir():
            for fichier in sorted(prefixe.iterdir()):
                if fichier.suffix.lower() in (".exe", ".dll") and fichier.is_file():
                    ajouter(f"{fichier.name} de l'interpréteur", fichier, False)
    ajouter("python.exe lancé", Path(sys.executable), False)
    chemins = sysconfig.get_paths()
    for libelle, cle in (("bibliothèque standard (Lib)", "stdlib"), ("site-packages", "purelib"),
                         ("site-packages", "platlib")):
        dossier = Path(chemins[cle])
        ajouter(libelle, dossier, True)
        ajouter(f"{libelle} (__pycache__)", dossier / "__pycache__", True)
        if cle != "stdlib" and dossier.is_dir():
            for fichier in sorted(dossier.iterdir()):
                if fichier.suffix.lower() == ".pth" or fichier.stem in ("sitecustomize", "usercustomize"):
                    ajouter(f"{fichier.name} de site-packages", fichier, fichier.is_dir())
    lib = Path(__file__).resolve().parents[1]
    ajouter("bibliothèques du poste", lib, True)
    for racine, dossiers, _fichiers in os.walk(lib):
        for nom in sorted(dossiers):
            ajouter("bibliothèques du poste", Path(racine) / nom, True)
    for nom in ("lancer.py", "ligne_etat.py", "acp-poste.cmd"):
        ajouter(f"{nom} du poste", lib.parent / nom, False)
    return cibles


def verifier_interpreteur(politique: Politique, *,
                          cibles: list[tuple[str, Path, bool]] | None = None) -> None:
    """Mode ``dedie``, au démarrage du service : refus si le compte du poste peut modifier l'interpréteur Python qui
    le lance ou une bibliothèque qu'il importe (relecture de P5, décision D67). Le service détient en mémoire le
    jeton machine et le jeton Claude déchiffrés : un exécutant mal confiné (P6) qui y injecterait du code les
    lirait. En mode ``proprietaire``, rien n'est vérifié (D51). Aucun chemin dans le message."""

    if politique.plateforme == "linux":
        _verifier_interpreteur_linux(cibles if cibles is not None else cibles_de_l_interpreteur_linux())
        return
    if not politique.compte_dedie:
        return
    for libelle, chemin, dossier in (cibles if cibles is not None else cibles_de_l_interpreteur()):
        obtenus = droits_d_ecriture_dossier(chemin) if dossier else droits_d_ecriture(chemin)
        if obtenus:
            raise PolitiqueRefusee(
                f"Interpréteur Python ou bibliothèques du poste modifiables par le compte du poste ({libelle} : "
                f"{', '.join(obtenus[:3])}) : un exécutant pourrait injecter du code dans le service, qui détient "
                "les jetons déchiffrés. Installez Python 3.12 de python.org pour tous les utilisateurs, sous "
                "Program Files, puis relancez l'installeur : refus de démarrer (décision D67).")


def cibles_de_l_interpreteur_linux() -> list[tuple[str, Path, bool]]:
    """Exécutant Linux (transposition de D67) : l'interpréteur réel, sa bibliothèque standard, ``site-packages`` et
    ses ``.pth`` (exécutés même sous ``-I``), puis les bibliothèques du poste, dossier par dossier."""
    import sysconfig

    vues: set[str] = set()
    cibles: list[tuple[str, Path, bool]] = []

    def ajouter(libelle: str, chemin: Path, dossier: bool) -> None:
        cle = os.path.realpath(chemin)
        if cle not in vues and os.path.lexists(chemin):
            vues.add(cle)
            cibles.append((libelle, Path(cle), dossier))

    ajouter("interpréteur Python", Path(sys.executable), False)
    chemins = sysconfig.get_paths()
    for libelle, cle in (("bibliothèque standard", "stdlib"), ("site-packages", "purelib"),
                         ("site-packages", "platlib")):
        dossier = Path(chemins[cle])
        ajouter(libelle, dossier, True)
        if cle != "stdlib" and dossier.is_dir():
            for fichier in sorted(dossier.iterdir()):
                if fichier.suffix == ".pth" or fichier.stem in ("sitecustomize", "usercustomize"):
                    ajouter(f"{fichier.name} de site-packages", fichier, fichier.is_dir())
    lib = Path(__file__).resolve().parents[1]
    ajouter("bibliothèques du poste", lib, True)
    for racine, dossiers, _fichiers in os.walk(lib):
        for nom in sorted(dossiers):
            ajouter("bibliothèques du poste", Path(racine) / nom, True)
    return cibles


def _verifier_interpreteur_linux(cibles: list[tuple[str, Path, bool]], proprietaire: int = 0) -> None:
    for libelle, chemin, _dossier in cibles:
        raison = _modifiable_par_un_agent(chemin, proprietaire)
        if raison and raison != "lien symbolique":
            raise PolitiqueRefusee(
                f"Interpréteur Python ou bibliothèques de l'exécutant modifiables par un agent ({libelle} : {raison}) : "
                "un agent pourrait injecter du code dans le superviseur, qui détient les jetons : refus de démarrer "
                "(décision D67).")


def modifiable_par_le_poste(politique: Politique) -> bool | None:
    """Pour le diagnostic : ``poste.toml`` modifiable par le compte courant (``None`` hors Windows)."""

    if os.name != "nt":
        return None
    try:
        return bool(droits_d_ecriture(politique.chemin))
    except OSError:
        return None
