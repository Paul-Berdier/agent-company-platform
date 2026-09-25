#!/usr/bin/env python3
"""Vérifie le catalogue de skills et de serveurs MCP d'ACP (étape P3).

Source de vérité : ``hermes/catalogue/catalogue.lock.json`` (schéma ``acp-catalogue/1``). Les
fichiers livrés dans l'image sont sous ``hermes/skills`` (``/opt/acp/skills``), les licences
tierces dans ``hermes/THIRD_PARTY.md`` (``/opt/acp/THIRD_PARTY.md``).

Règles vérifiées hors ligne (code 1 et message en français au premier écart, tous les écarts
listés) :

1. **Empreintes** : chaque fichier de ``hermes/skills`` figure au verrou et inversement ; SHA-256
   égaux ; pour un fichier vendorisé, blob git égal (empreinte ``git hash-object``).
2. **Licences** : chaque source vendorisée a son ``LICENSE`` (copie exacte, au verrou), une licence
   libre admise (MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause), un ``PROVENANCE.md`` cohérent
   (dépôt, commit, chaque skill et son chemin amont) et une section de ``THIRD_PARTY.md`` qui
   reprend le texte exact de la licence.
3. **Noms** : ``name`` du frontmatter = nom du dossier = nom au verrou.
4. **Collisions** refusées : entre skills du catalogue, avec les skills livrées par Hermes (58) et
   ses skills optionnelles (150), avec les noms exclus.
5. **Exclusions** : aucune skill ``anthropics/skills`` ``docx``, ``pdf``, ``pptx``, ``xlsx``, aucune
   source à licence non libre, aucun fichier d'une skill exclue.
6. **Texte seul** pour la cible ``hermes`` (l'agent n'a aucun outil d'exécution sur Railway) :
   seulement des ``.md``, aucun dossier ``scripts/``, aucun bit exécutable, aucun ``!`cmd```,
   aucune clé ``metadata.hermes.config``.
7. **Garde et managed scope** : les outils de chaque serveur MCP actif côté Hermes sont les noms
   que Hermes leur donne (``mcp__<serveur>__<outil>``), figurent dans ``OUTILS_ADMIS`` de la garde
   (lu par l'AST de ``garde_execution.py``) ; l'URL, la liste blanche des outils, l'échantillonnage
   et l'élicitation coupés sont épinglés dans ``EPINGLES_OBLIGATOIRES`` (lu par l'AST de
   ``acp_demarrage.py``, que la construction de l'image confronte à ``hermes/gere/config.yaml``) ;
   le serveur est nommé dans ``platform_toolsets.cli`` ; ``skills.external_dirs`` et
   ``skills.disabled`` ne sont PAS épinglés (Hermes lit ces deux listes dans le config.yaml du
   volume, sans la managed scope : docs/refonte/catalogue.md).
8. **Skills livrées par Hermes** : chacune classée une fois (désactivée par ACP, gardée ou réservée
   à macOS) ; ``hermes-agent`` jamais désactivée.
9. **Profils** : chaque nom cité existe (catalogue ou livrée gardée), chaque skill porte les profils
   qui la citent, et la skill ``acp-profils`` les nomme tous.

``--amont`` (réseau) : télécharge chaque fichier vendorisé et chaque ``LICENSE`` au commit épinglé
(``https://raw.githubusercontent.com/<dépôt>/<commit>/<chemin>``) et les compare octet pour octet ;
exige qu'aucun ``NOTICE`` amont n'existe (il faudrait le livrer).

Bibliothèque standard seulement. Usage :
    python scripts/verifier_catalogue.py [--amont]
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

RACINE = Path(__file__).resolve().parents[1]
SCHEMA = "acp-catalogue/1"
LICENCES_LIBRES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause"}
ANTHROPIC_INTERDITES = {"docx", "pdf", "pptx", "xlsx"}
ESSENTIELLES = {"hermes-agent"}
ETATS_SKILL = {"hermes": {"livree"}, "poste": {"reportee-p8"}}
PROFILS_ATTENDUS = {"base", "web", "recherche", "donnees"}
_NOM_SKILL = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHELL_EN_LIGNE = re.compile(r"!`[^`\n]+`")


class Chemins:
    """Emplacements vérifiés ; les tests en passent d'autres (copie du dépôt)."""

    def __init__(self, racine: Path = RACINE) -> None:
        self.racine = racine
        self.verrou = racine / "hermes" / "catalogue" / "catalogue.lock.json"
        self.skills = racine / "hermes" / "skills"
        self.tiers = racine / "hermes" / "THIRD_PARTY.md"
        self.garde = racine / "hermes" / "plugins" / "acp-poste" / "garde_execution.py"
        self.demarrage = racine / "hermes" / "image" / "acp_demarrage.py"


# --------------------------------------------------------------------------------------------- outils


def sha256(donnees: bytes) -> str:
    return hashlib.sha256(donnees).hexdigest()


def blob_git(donnees: bytes) -> str:
    """Empreinte d'un blob git (``git hash-object``) : SHA-1 de « blob <taille>\\0 » + contenu."""
    return hashlib.sha1(b"blob %d\0" % len(donnees) + donnees).hexdigest()


def nom_mcp_hermes(serveur: str, outil: str) -> str:
    """Nom d'un outil MCP dans Hermes 0.21.5 : ``mcp__<serveur>__<outil>``, tout caractère hors de
    ``[A-Za-z0-9_]`` remplacé par « _ » (tools/mcp_tool_schema.py:147-185 ; au-delà de 64
    caractères Hermes tronque avec un suffixe haché : refusé ici)."""
    propre = lambda texte: re.sub(r"[^A-Za-z0-9_]", "_", texte)  # noqa: E731
    return f"mcp__{propre(serveur)}__{propre(outil)}"


def frontmatter(texte: str) -> Tuple[Optional[str], Set[str]]:
    """(``name`` de premier niveau, chemins pointés des clés) du frontmatter YAML d'un SKILL.md.

    Lecture volontairement réduite (bibliothèque standard) : clés ``cle:`` indentées par des
    espaces ; la lecture complète par le chargeur de Hermes est vérifiée dans l'image
    (hermes/tests/image/test_catalogue.py)."""
    lignes = texte.split("\n")
    if not lignes or lignes[0].rstrip("\r") != "---":
        return None, set()
    nom: Optional[str] = None
    cles: Set[str] = set()
    pile: List[Tuple[int, str]] = []
    for ligne in lignes[1:]:
        ligne = ligne.rstrip("\r")
        if ligne == "---":
            break
        correspondance = re.match(r"^( *)([A-Za-z0-9_.-]+):(?:\s(.*)|$)", ligne)
        if not correspondance:
            continue
        retrait, cle, valeur = len(correspondance.group(1)), correspondance.group(2), correspondance.group(3)
        while pile and pile[-1][0] >= retrait:
            pile.pop()
        chemin = ".".join([c for _, c in pile] + [cle])
        cles.add(chemin)
        pile.append((retrait, cle))
        if chemin == "name" and valeur is not None:
            valeur = valeur.strip()
            if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
                valeur = valeur[1:-1]
            nom = valeur
    return nom, cles


def _constante_ast(fichier: Path, nom: str) -> Any:
    """Valeur littérale d'une constante de module (``NOM = …`` ou ``NOM: type = …``), lue par l'AST
    sans importer le module ; ``frozenset({...})`` est accepté."""
    arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
    for noeud in arbre.body:
        cible, valeur = None, None
        if isinstance(noeud, ast.Assign) and len(noeud.targets) == 1:
            cible, valeur = noeud.targets[0], noeud.value
        elif isinstance(noeud, ast.AnnAssign):
            cible, valeur = noeud.target, noeud.value
        if isinstance(cible, ast.Name) and cible.id == nom and valeur is not None:
            if (isinstance(valeur, ast.Call) and isinstance(valeur.func, ast.Name)
                    and valeur.func.id == "frozenset" and len(valeur.args) == 1):
                return frozenset(ast.literal_eval(valeur.args[0]))
            return ast.literal_eval(valeur)
    raise KeyError(f"constante {nom} introuvable dans {fichier}")


def _modes_git(chemins: Chemins) -> Optional[Dict[str, str]]:
    """Modes des fichiers de hermes/skills dans l'index git (100644, 100755…) ; None hors d'un dépôt
    git (le bit exécutable de l'index fait foi sous Windows, où le système de fichiers n'en a pas)."""
    try:
        sortie = subprocess.run(["git", "-C", str(chemins.racine), "ls-files", "-s", "--", "hermes/skills"],
                                capture_output=True, text=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    modes: Dict[str, str] = {}
    for ligne in sortie.splitlines():
        entete, _, chemin = ligne.partition("\t")
        if entete:
            modes[chemin] = entete.split()[0]
    return modes


# --------------------------------------------------------------------------------------------- règles


class Verification:
    def __init__(self, chemins: Chemins) -> None:
        self.chemins = chemins
        self.erreurs: List[str] = []
        self.verrou: Dict[str, Any] = {}

    def erreur(self, message: str) -> None:
        self.erreurs.append(message)

    # -- chargement ------------------------------------------------------------------------------

    def charger(self) -> bool:
        try:
            self.verrou = json.loads(self.chemins.verrou.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.erreur(f"le verrou {self.chemins.verrou} ne se lit pas : {exc}.")
            return False
        if not isinstance(self.verrou, dict) or self.verrou.get("schema") != SCHEMA:
            self.erreur(f"le verrou doit déclarer le schéma « {SCHEMA} ».")
            return False
        for cle, genre in (("sources", dict), ("categories", dict), ("skills", list), ("livrees", dict),
                           ("mcp", list), ("profils", dict), ("exclus", list), ("hermes", dict)):
            if not isinstance(self.verrou.get(cle), genre):
                self.erreur(f"le verrou n'a pas de champ « {cle} » du bon type.")
        return not self.erreurs

    @property
    def sources(self) -> Dict[str, Dict[str, Any]]:
        return self.verrou["sources"]

    @property
    def skills(self) -> List[Dict[str, Any]]:
        return self.verrou["skills"]

    def skills_cible(self, cible: str) -> List[Dict[str, Any]]:
        return [s for s in self.skills if isinstance(s, dict) and s.get("cible") == cible]

    # -- règle 1 : empreintes --------------------------------------------------------------------

    def fichiers_attendus(self) -> Dict[str, Tuple[Dict[str, Any], bool]]:
        """{chemin relatif sous hermes/skills : (entrée du verrou, vendorisé ?)}."""
        attendus: Dict[str, Tuple[Dict[str, Any], bool]] = {}
        for categorie, bloc in self.verrou["categories"].items():
            source = next((s for s in self.sources.values() if s.get("categorie") == categorie), None)
            vendorisee = bool(source and source.get("vendorisee"))
            for nom, entree in (bloc.get("fichiers") or {}).items():
                attendus[f"{categorie}/{nom}"] = (entree, vendorisee and nom == "LICENSE")
        for skill in self.skills_cible("hermes"):
            source = self.sources.get(skill.get("source")) or {}
            for nom, entree in (skill.get("fichiers") or {}).items():
                attendus[f"{skill.get('chemin')}/{nom}"] = (entree, bool(source.get("vendorisee")))
        return attendus

    def regle_empreintes(self) -> None:
        racine = self.chemins.skills
        presents: Dict[str, bytes] = {}
        if not racine.is_dir():
            self.erreur(f"{racine} est absent.")
            return
        for chemin in sorted(racine.rglob("*")):
            relatif = chemin.relative_to(racine).as_posix()
            if chemin.is_symlink():
                self.erreur(f"hermes/skills/{relatif} est un lien symbolique : refusé.")
            elif chemin.is_file():
                presents[relatif] = chemin.read_bytes()
        attendus = self.fichiers_attendus()
        for relatif in sorted(set(presents) - set(attendus)):
            self.erreur(f"hermes/skills/{relatif} n'est pas au verrou (fichier ajouté hors catalogue).")
        for relatif in sorted(set(attendus) - set(presents)):
            self.erreur(f"hermes/skills/{relatif} est au verrou mais absent du dépôt.")
        for relatif in sorted(set(attendus) & set(presents)):
            entree, vendorise = attendus[relatif]
            donnees = presents[relatif]
            if not isinstance(entree, dict) or not _SHA256.match(str(entree.get("sha256", ""))):
                self.erreur(f"hermes/skills/{relatif} : empreinte SHA-256 absente ou mal formée au verrou.")
                continue
            if sha256(donnees) != entree["sha256"]:
                self.erreur(f"hermes/skills/{relatif} a été modifié : SHA-256 {sha256(donnees)} au lieu de "
                            f"{entree['sha256']} (verrou).")
            if vendorise or "blob_git" in entree:
                if not _SHA1.match(str(entree.get("blob_git", ""))):
                    self.erreur(f"hermes/skills/{relatif} : blob git absent ou mal formé au verrou.")
                elif blob_git(donnees) != entree["blob_git"]:
                    self.erreur(f"hermes/skills/{relatif} : blob git {blob_git(donnees)} au lieu de "
                                f"{entree['blob_git']} (le fichier n'est plus celui du dépôt amont).")

    # -- règle 2 : licences et provenance --------------------------------------------------------

    def regle_licences(self) -> None:
        try:
            tiers = self.chemins.tiers.read_text(encoding="utf-8")
        except OSError as exc:
            self.erreur(f"{self.chemins.tiers} ne se lit pas : {exc}.")
            tiers = ""
        for id_source, source in self.sources.items():
            if not isinstance(source, dict):
                self.erreur(f"source {id_source} mal formée au verrou.")
                continue
            if not source.get("vendorisee"):
                continue
            categorie = source.get("categorie")
            if source.get("licence") not in LICENCES_LIBRES:
                self.erreur(f"source {id_source} : licence « {source.get('licence')} » hors de la liste admise "
                            f"({', '.join(sorted(LICENCES_LIBRES))}) : non vendorisable dans un dépôt public.")
            for champ in ("url", "commit", "auteur", "categorie"):
                if not source.get(champ):
                    self.erreur(f"source {id_source} : champ « {champ} » absent au verrou.")
            if not _SHA1.match(str(source.get("commit", ""))):
                self.erreur(f"source {id_source} : commit épinglé mal formé (40 caractères hexadécimaux attendus).")
            if source.get("url") != f"https://github.com/{id_source}":
                self.erreur(f"source {id_source} : URL « {source.get('url')} » différente du dépôt déclaré.")
            fichiers = ((self.verrou["categories"].get(categorie) or {}).get("fichiers") or {})
            for requis in ("LICENSE", "PROVENANCE.md", "DESCRIPTION.md"):
                if requis not in fichiers:
                    self.erreur(f"source {id_source} : {categorie}/{requis} absent du verrou.")
            licence_chemin = self.chemins.skills / str(categorie) / "LICENSE"
            try:
                licence = licence_chemin.read_text(encoding="utf-8")
            except OSError:
                self.erreur(f"source {id_source} : {licence_chemin} absent (licence non livrée).")
                licence = ""
            try:
                provenance = (self.chemins.skills / str(categorie) / "PROVENANCE.md").read_text(encoding="utf-8")
            except OSError:
                provenance = ""
            for attendu in (str(source.get("url")), str(source.get("commit"))):
                if attendu not in provenance:
                    self.erreur(f"source {id_source} : PROVENANCE.md ne cite pas « {attendu} ».")
            for skill in self.skills_cible("hermes"):
                if skill.get("source") != id_source:
                    continue
                for fichier in skill.get("fichiers") or {}:
                    for attendu in (f"`{skill.get('nom')}/{fichier}`", f"`{skill.get('chemin_amont')}/{fichier}`"):
                        if attendu not in provenance:
                            self.erreur(f"source {id_source} : PROVENANCE.md ne cite pas {attendu}.")
            section = re.search(rf"^## {re.escape(id_source)}\n(.*?)(?=^## |\Z)", tiers, re.S | re.M)
            if not section:
                self.erreur(f"source {id_source} : aucune section « ## {id_source} » dans THIRD_PARTY.md.")
                continue
            texte = section.group(1)
            for attendu in (str(source.get("url")), str(source.get("commit")), str(source.get("licence"))):
                if attendu not in texte:
                    self.erreur(f"source {id_source} : THIRD_PARTY.md ne cite pas « {attendu} ».")
            if licence and licence.strip() not in texte:
                self.erreur(f"source {id_source} : THIRD_PARTY.md ne reprend pas le texte exact de LICENSE.")

    # -- règles 3 à 6 : noms, collisions, exclusions, texte seul ---------------------------------

    def regle_noms_et_texte(self) -> None:
        modes = _modes_git(self.chemins)
        vus: Dict[str, int] = {}
        for skill in self.skills:
            if not isinstance(skill, dict):
                self.erreur("une entrée de « skills » n'est pas un objet.")
                continue
            nom = str(skill.get("nom", ""))
            vus[nom] = vus.get(nom, 0) + 1
            cible = skill.get("cible")
            if not _NOM_SKILL.match(nom):
                self.erreur(f"skill « {nom} » : nom invalide (minuscules, chiffres, tirets, 64 au plus).")
            if cible not in ETATS_SKILL:
                self.erreur(f"skill {nom} : cible « {cible} » inconnue (hermes ou poste).")
                continue
            if skill.get("etat") not in ETATS_SKILL[cible]:
                self.erreur(f"skill {nom} : état « {skill.get('etat')} » invalide pour la cible {cible}.")
            if skill.get("source") not in self.sources:
                self.erreur(f"skill {nom} : source « {skill.get('source')} » absente de « sources ».")
            for champ in ("description_fr", "raison"):
                if not skill.get(champ):
                    self.erreur(f"skill {nom} : champ « {champ} » absent.")
            if cible == "poste":
                if skill.get("fichiers") or (self.chemins.skills / str(skill.get("chemin", "\0"))).exists():
                    self.erreur(f"skill {nom} : cible poste, elle ne doit pas être livrée dans l'image en P3.")
                continue
            if skill.get("execution") != "aucune":
                self.erreur(f"skill {nom} : cible hermes, « execution » doit valoir « aucune ».")
            source = self.sources.get(skill.get("source")) or {}
            chemin = str(skill.get("chemin", ""))
            if chemin != f"{source.get('categorie')}/{nom}":
                self.erreur(f"skill {nom} : chemin « {chemin} » ; attendu « {source.get('categorie')}/{nom} » "
                            "(dossier = nom de la skill).")
            if source.get("vendorisee") and not skill.get("chemin_amont"):
                self.erreur(f"skill {nom} : chemin amont absent au verrou.")
            fichiers = skill.get("fichiers") or {}
            if "SKILL.md" not in fichiers:
                self.erreur(f"skill {nom} : SKILL.md absent du verrou.")
            dossier = self.chemins.skills / chemin
            for fichier in fichiers:
                if not fichier.endswith(".md") or "/" in fichier.replace("\\", "/"):
                    self.erreur(f"skill {nom} : « {fichier} » n'est pas un texte Markdown de premier niveau "
                                "(cible hermes : texte seul).")
            if dossier.is_dir():
                for element in sorted(dossier.rglob("*")):
                    relatif = element.relative_to(self.chemins.skills).as_posix()
                    if element.is_dir():
                        self.erreur(f"hermes/skills/{relatif} : sous-dossier refusé (scripts/ ou autre) "
                                    "pour une skill exécutée par Hermes.")
                        continue
                    if not element.name.endswith(".md"):
                        self.erreur(f"hermes/skills/{relatif} : seul le Markdown est admis (texte seul).")
                    mode = (modes or {}).get(f"hermes/skills/{relatif}")
                    if mode not in (None, "100644") or (modes is None and os.name != "nt"
                                                        and element.stat().st_mode & stat.S_IXUSR):
                        self.erreur(f"hermes/skills/{relatif} : fichier exécutable refusé.")
                    try:
                        texte = element.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        self.erreur(f"hermes/skills/{relatif} : texte UTF-8 illisible.")
                        continue
                    if _SHELL_EN_LIGNE.search(texte):
                        self.erreur(f"hermes/skills/{relatif} : commande « !`…` » refusée (skills.inline_shell).")
            skill_md = dossier / "SKILL.md"
            try:
                nom_declare, cles = frontmatter(skill_md.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            if nom_declare != nom:
                self.erreur(f"skill {nom} : le frontmatter déclare « {nom_declare} » (nom, dossier et verrou "
                            "doivent concorder).")
            if any(c == "metadata.hermes.config" or c.startswith("metadata.hermes.config.") for c in cles):
                self.erreur(f"skill {nom} : clé metadata.hermes.config refusée (réglages exposés à l'agent).")
        for nom, compte in sorted(vus.items()):
            if compte > 1:
                self.erreur(f"collision : la skill « {nom} » apparaît {compte} fois au catalogue.")
        livrees = self.verrou["livrees"]
        noms_livres = set(livrees.get("noms") or [])
        optionnelles = set(livrees.get("optionnelles") or [])
        exclus = {str(e.get("nom")): e for e in self.verrou["exclus"] if isinstance(e, dict)}
        for nom in sorted(vus):
            if nom in noms_livres:
                self.erreur(f"collision : « {nom} » est aussi une skill livrée par Hermes (skill_view refuserait "
                            "un nom ambigu : tools/skills_tool.py).")
            if nom in optionnelles:
                self.erreur(f"collision : « {nom} » est aussi une skill optionnelle de Hermes.")
            if nom in exclus:
                self.erreur(f"« {nom} » est au catalogue ET dans les exclus ({exclus[nom].get('raison')}).")
        if len(noms_livres) != len(livrees.get("noms") or []) or len(optionnelles) != len(livrees.get("optionnelles") or []):
            self.erreur("les listes des skills livrées ou optionnelles de Hermes contiennent des doublons.")
        for id_source, source in self.sources.items():
            if id_source == "anthropics/skills" and source.get("vendorisee"):
                self.erreur("anthropics/skills ne peut pas être vendorisé (licence propriétaire pour docx, pdf, "
                            "pptx, xlsx).")
        for skill in self.skills:
            if isinstance(skill, dict) and skill.get("source") == "anthropics/skills" and skill.get("nom") in ANTHROPIC_INTERDITES:
                self.erreur(f"la skill {skill.get('nom')} d'anthropics/skills est refusée (licence propriétaire).")
        for nom in ANTHROPIC_INTERDITES:
            if exclus.get(nom, {}).get("source") != "anthropics/skills":
                self.erreur(f"l'exclusion de « {nom} » (anthropics/skills, licence propriétaire) manque au verrou.")
        for nom, entree in exclus.items():
            if not entree.get("raison"):
                self.erreur(f"exclusion « {nom} » sans raison.")
        if "agent-reach" not in exclus:
            self.erreur("l'exclusion d'agent-reach (décision du propriétaire) manque au verrou.")
        for dossier in (self.chemins.skills.glob("*/*") if self.chemins.skills.is_dir() else []):
            if dossier.is_dir() and dossier.name in exclus:
                self.erreur(f"hermes/skills/{dossier.relative_to(self.chemins.skills).as_posix()} : skill exclue livrée.")

    # -- règle 7 : garde et managed scope --------------------------------------------------------

    def regle_mcp(self) -> None:
        try:
            admis = _constante_ast(self.chemins.garde, "OUTILS_ADMIS")
        except (OSError, SyntaxError, ValueError, KeyError) as exc:
            self.erreur(f"OUTILS_ADMIS illisible dans {self.chemins.garde} : {exc}.")
            admis = frozenset()
        try:
            epingles = dict(_constante_ast(self.chemins.demarrage, "EPINGLES_OBLIGATOIRES"))
        except (OSError, SyntaxError, ValueError, KeyError, TypeError) as exc:
            self.erreur(f"EPINGLES_OBLIGATOIRES illisible dans {self.chemins.demarrage} : {exc}.")
            epingles = {}
        actifs = []
        for serveur in self.verrou["mcp"]:
            if not isinstance(serveur, dict):
                self.erreur("une entrée de « mcp » n'est pas un objet.")
                continue
            nom = str(serveur.get("nom", ""))
            if serveur.get("cible") == "poste":
                if serveur.get("etat") != "reporte-p8":
                    self.erreur(f"MCP {nom} : cible poste, état « reporte-p8 » attendu en P3.")
                for cle in epingles:
                    if cle.startswith(f"mcp_servers.{nom}."):
                        self.erreur(f"MCP {nom} : cible poste, il ne doit pas être épinglé côté Hermes ({cle}).")
                continue
            if serveur.get("cible") != "hermes" or serveur.get("etat") != "actif":
                self.erreur(f"MCP {nom} : cible et état inconnus ({serveur.get('cible')}, {serveur.get('etat')}).")
                continue
            actifs.append(nom)
            if serveur.get("transport") != "http" or not str(serveur.get("url", "")).startswith("https://"):
                self.erreur(f"MCP {nom} : seul un serveur distant en https est admis côté Hermes (aucun processus "
                            "lancé dans le conteneur).")
            if serveur.get("echantillonnage") is not False or serveur.get("elicitation") is not False:
                self.erreur(f"MCP {nom} : échantillonnage et élicitation doivent être coupés.")
            amont = list(serveur.get("outils_amont") or [])
            noms = [nom_mcp_hermes(nom, o) for o in amont]
            if not amont or noms != list(serveur.get("outils_hermes") or []):
                self.erreur(f"MCP {nom} : outils_hermes {serveur.get('outils_hermes')} ; Hermes les nomme {noms}.")
            for outil in noms:
                if len(outil) > 64:
                    self.erreur(f"MCP {nom} : le nom {outil} dépasse 64 caractères (Hermes le tronquerait).")
                if outil not in admis:
                    self.erreur(f"MCP {nom} : l'outil {outil} n'est pas dans OUTILS_ADMIS de la garde : il serait "
                                "refusé à chaque appel.")
            attendues = {
                f"mcp_servers.{nom}.url": serveur.get("url"),
                f"mcp_servers.{nom}.enabled": True,
                f"mcp_servers.{nom}.ssl_verify": True,
                f"mcp_servers.{nom}.sampling.enabled": False,
                f"mcp_servers.{nom}.elicitation.enabled": False,
                f"mcp_servers.{nom}.tools.include": amont,
                f"mcp_servers.{nom}.tools.resources": False,
                f"mcp_servers.{nom}.tools.prompts": False,
            }
            for cle, valeur in attendues.items():
                if cle not in epingles:
                    self.erreur(f"MCP {nom} : l'épingle {cle} manque à EPINGLES_OBLIGATOIRES.")
                elif epingles[cle] != valeur or type(epingles[cle]) is not type(valeur):
                    self.erreur(f"MCP {nom} : l'épingle {cle} vaut {epingles[cle]!r}, attendu {valeur!r}.")
            if nom not in (epingles.get("platform_toolsets.cli") or []):
                self.erreur(f"MCP {nom} : absent de platform_toolsets.cli (l'outil ne serait jamais offert).")
        mcp_admis = sorted(o for o in admis if o.startswith("mcp__"))
        attendus = sorted(nom_mcp_hermes(s["nom"], o) for s in self.verrou["mcp"] if isinstance(s, dict)
                          and s.get("nom") in actifs for o in s.get("outils_amont") or [])
        if mcp_admis != attendus:
            self.erreur(f"OUTILS_ADMIS admet les outils MCP {mcp_admis} ; le catalogue n'en déclare que {attendus}.")
        for plateforme in ("api_server", "cron"):
            liste = epingles.get(f"platform_toolsets.{plateforme}") or []
            if "no_mcp" not in liste or any(n in liste for n in actifs):
                self.erreur(f"platform_toolsets.{plateforme} doit garder no_mcp (aucun serveur MCP).")
        serveurs_epingles = {c.split(".")[1] for c in epingles if c.startswith("mcp_servers.")}
        for nom in sorted(serveurs_epingles - set(actifs)):
            self.erreur(f"le serveur MCP {nom} est épinglé mais absent du catalogue (ou non actif).")
        for cle in ("skills.external_dirs", "skills.disabled"):
            if any(c == cle or c.startswith(cle + ".") for c in epingles):
                self.erreur(f"{cle} ne doit PAS être épinglé : Hermes le lit dans le config.yaml du volume sans la "
                            "managed scope, et une clé épinglée est retirée du volume à chaque sauvegarde.")

    # -- règles 8 et 9 : skills livrées et profils -----------------------------------------------

    def regle_livrees_et_profils(self) -> None:
        livrees = self.verrou["livrees"]
        noms_livres = set(livrees.get("noms") or [])
        desactivees = [str(e.get("nom")) for e in livrees.get("desactivees_par_acp") or [] if isinstance(e, dict)]
        gardees = [str(e.get("nom")) for e in livrees.get("gardees") or [] if isinstance(e, dict)]
        macos = list(livrees.get("macos_seulement") or [])
        for groupe, liste in (("desactivees_par_acp", desactivees), ("gardees", gardees), ("macos_seulement", macos)):
            for nom in liste:
                if nom not in noms_livres:
                    self.erreur(f"livrées : « {nom} » ({groupe}) n'est pas une skill livrée par Hermes.")
        for e in (livrees.get("desactivees_par_acp") or []) + (livrees.get("gardees") or []):
            if isinstance(e, dict) and not e.get("raison"):
                self.erreur(f"livrées : « {e.get('nom')} » sans raison.")
        comptes: Dict[str, int] = {}
        for nom in desactivees + gardees + macos:
            comptes[nom] = comptes.get(nom, 0) + 1
        for nom in sorted(noms_livres):
            if comptes.get(nom, 0) != 1:
                self.erreur(f"livrées : « {nom} » doit être classée exactement une fois (désactivée, gardée ou "
                            f"macOS) ; trouvée {comptes.get(nom, 0)} fois.")
        for nom in ESSENTIELLES:
            if nom in desactivees:
                self.erreur(f"livrées : « {nom} » est essentielle et ne peut pas être désactivée.")
        profils = self.verrou["profils"]
        if set(profils) != PROFILS_ATTENDUS:
            self.erreur(f"profils : {sorted(profils)} ; attendus {sorted(PROFILS_ATTENDUS)}.")
        catalogue = {s.get("nom"): s for s in self.skills if isinstance(s, dict)}
        mcp = {s.get("nom"): s for s in self.verrou["mcp"] if isinstance(s, dict)}
        cites: Dict[str, Set[str]] = {}
        for id_profil, profil in profils.items():
            if not isinstance(profil, dict) or not profil.get("libelle"):
                self.erreur(f"profil {id_profil} : mal formé (libellé absent).")
                continue
            for nom in profil.get("skills_hermes") or []:
                cites.setdefault(nom, set()).add(id_profil)
                if nom in catalogue:
                    if catalogue[nom].get("cible") != "hermes":
                        self.erreur(f"profil {id_profil} : {nom} n'est pas une skill côté Hermes.")
                elif nom not in gardees:
                    self.erreur(f"profil {id_profil} : {nom} n'est ni au catalogue ni une skill livrée gardée.")
            for nom in profil.get("mcp_hermes") or []:
                if (mcp.get(nom) or {}).get("cible") != "hermes":
                    self.erreur(f"profil {id_profil} : le MCP {nom} n'est pas actif côté Hermes.")
            for nom in profil.get("poste") or []:
                cites.setdefault(nom, set()).add(id_profil)
                cible = (catalogue.get(nom) or mcp.get(nom) or {}).get("cible")
                if cible != "poste":
                    self.erreur(f"profil {id_profil} : {nom} (poste) n'est ni une skill ni un MCP reporté au poste.")
        # Une skill du catalogue (et un MCP reporté au poste) porte exactement les profils qui la citent ;
        # un MCP actif côté Hermes appartient au profil « base », donc à tous les profils.
        for nom, entree in list(catalogue.items()) + list(mcp.items()):
            declares = set(entree.get("profils") or [])
            if nom in mcp and entree.get("cible") == "hermes":
                if declares != {"base"}:
                    self.erreur(f"MCP {nom} : profils déclarés {sorted(declares)} ; attendu [\"base\"].")
                for id_profil, profil in profils.items():
                    if isinstance(profil, dict) and nom not in (profil.get("mcp_hermes") or []):
                        self.erreur(f"profil {id_profil} : le MCP de base {nom} manque à mcp_hermes.")
                continue
            attendus = cites.get(nom, set())
            if declares != attendus:
                self.erreur(f"{nom} : profils déclarés {sorted(declares)} ; cité par {sorted(attendus)}.")
        profils_skill = catalogue.get("acp-profils")
        if profils_skill:
            try:
                texte = (self.chemins.skills / str(profils_skill.get("chemin")) / "SKILL.md").read_text(encoding="utf-8")
            except OSError:
                texte = ""
            for profil in profils.values():
                if not isinstance(profil, dict):
                    continue
                for nom in (profil.get("skills_hermes") or []) + (profil.get("mcp_hermes") or []) + [
                        n for n in profil.get("poste") or [] if n in catalogue]:
                    if f"`{nom}`" not in texte:
                        self.erreur(f"la skill acp-profils ne cite pas `{nom}` (profils du verrou).")
        else:
            self.erreur("la skill maison acp-profils manque au catalogue.")

    # -- --amont ---------------------------------------------------------------------------------

    def regle_amont(self, telecharger) -> None:
        for id_source, source in self.sources.items():
            if not isinstance(source, dict) or not source.get("vendorisee"):
                continue
            commit = source.get("commit")
            categorie = source.get("categorie")
            fichiers: List[Tuple[str, str]] = [("LICENSE", f"{categorie}/LICENSE")]
            for skill in self.skills_cible("hermes"):
                if skill.get("source") == id_source:
                    fichiers += [(f"{skill['chemin_amont']}/{f}", f"{skill['chemin']}/{f}") for f in skill.get("fichiers") or {}]
            for amont, local in fichiers:
                url = f"https://raw.githubusercontent.com/{id_source}/{commit}/{amont}"
                try:
                    distant = telecharger(url)
                except Exception as exc:  # noqa: BLE001 — toute erreur réseau est un échec de vérification
                    self.erreur(f"amont : {url} injoignable ({type(exc).__name__} : {exc}) : vérification impossible.")
                    continue
                if distant is None:
                    self.erreur(f"amont : {url} n'existe pas (404) au commit épinglé.")
                    continue
                try:
                    present = (self.chemins.skills / local).read_bytes()
                except OSError:
                    present = b""
                if present != distant:
                    self.erreur(f"amont : hermes/skills/{local} diffère de {url} (SHA-256 {sha256(present)[:16]}… "
                                f"contre {sha256(distant)[:16]}…).")
            for notice in ("NOTICE", "NOTICE.md", "NOTICE.txt"):
                url = f"https://raw.githubusercontent.com/{id_source}/{commit}/{notice}"
                try:
                    if telecharger(url) is not None:
                        self.erreur(f"amont : {id_source} publie un fichier {notice} : il doit être livré avec ses skills.")
                except Exception as exc:  # noqa: BLE001
                    self.erreur(f"amont : {url} injoignable ({type(exc).__name__}) : vérification impossible.")

    def tout(self, *, amont: bool = False, telecharger=None) -> List[str]:
        if not self.charger():
            return self.erreurs
        self.regle_empreintes()
        self.regle_licences()
        self.regle_noms_et_texte()
        self.regle_mcp()
        self.regle_livrees_et_profils()
        if amont:
            self.regle_amont(telecharger or telecharger_https)
        return self.erreurs


def telecharger_https(url: str) -> Optional[bytes]:
    """Contenu d'une URL https (None sur 404). Aucune autre adresse n'est admise."""
    if not url.startswith("https://raw.githubusercontent.com/"):
        raise ValueError(f"adresse refusée : {url}")
    requete = urllib.request.Request(url, headers={"User-Agent": "acp-verifier-catalogue"})
    try:
        with urllib.request.urlopen(requete, timeout=60) as reponse:  # noqa: S310 — https fixe
            return reponse.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def resume(verification: Verification) -> str:
    verrou = verification.verrou
    hermes = [s for s in verrou.get("skills", []) if s.get("cible") == "hermes"]
    poste = [s for s in verrou.get("skills", []) if s.get("cible") == "poste"]
    mcp = [m.get("nom") for m in verrou.get("mcp", []) if m.get("cible") == "hermes"]
    livrees = verrou.get("livrees", {})
    return (f"{len(hermes)} skills livrées dans l'image ({sum(1 for s in hermes if s.get('source') != 'acp')} "
            f"vendorisées, {sum(1 for s in hermes if s.get('source') == 'acp')} maison), {len(poste)} reportées au poste, "
            f"MCP côté Hermes : {', '.join(mcp) or 'aucun'} ; skills de Hermes : "
            f"{len(livrees.get('desactivees_par_acp', []))} désactivées, {len(livrees.get('gardees', []))} gardées, "
            f"{len(livrees.get('macos_seulement', []))} réservées à macOS.")


def main(argv: Optional[Iterable[str]] = None) -> int:
    analyseur = argparse.ArgumentParser(description="Vérifie le catalogue de skills et de MCP d'ACP.")
    analyseur.add_argument("--amont", action="store_true",
                           help="compare aussi chaque fichier vendorisé au dépôt amont (réseau)")
    options = analyseur.parse_args(list(argv) if argv is not None else None)
    verification = Verification(Chemins())
    erreurs = verification.tout(amont=options.amont)
    if erreurs:
        print(f"Catalogue refusé : {len(erreurs)} écart(s).", file=sys.stderr)
        for erreur in erreurs:
            print(f"  - {erreur}", file=sys.stderr)
        return 1
    print("Catalogue conforme : " + resume(verification)
          + (" Fichiers identiques au dépôt amont." if options.amont else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
