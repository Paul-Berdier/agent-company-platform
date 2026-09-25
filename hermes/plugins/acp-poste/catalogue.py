"""Catalogue d'ACP vu par le greffon (étape P3) : ``GET /api/plugins/acp-poste/v1/catalogue`` et
bloc ``catalogue`` de ``/v1/meta``.

Deux sources, jamais confondues :

- le **verrou** livré dans l'image (``/opt/acp/catalogue/catalogue.lock.json``), en lecture seule :
  sources, skills, serveurs MCP, profils, exclusions ;
- l'**état vu par le chargeur de skills de Hermes** dans le processus qui sert la route (le tableau
  de bord) : ``skills.external_dirs`` et ``skills.disabled`` tels que Hermes les lit (dans le
  config.yaml du volume, SANS la managed scope : agent/skill_utils.py:250-385), emplacements réels
  de chaque skill, état du client MCP.

Ce module est le SEUL du greffon qui importe les internes des skills et des MCP de Hermes, chacun
depuis son module de définition (agent.skill_utils, hermes_constants, tools.mcp_tool_config,
tools.mcp_tool_discovery), jamais par un pointeur PLUGIN-COMPAT ; ``hermes plugins compat`` et les
tests de l'image épinglée le vérifient. Aucune valeur n'est inventée : ce qui ne peut pas être lu
vaut ``None`` (« Inconnu ») ou ``"inconnu"`` et produit une alerte en français.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

SDK_ATTENDU = "1.x"
ETATS_CONNEXION = {"connected": "connecte", "failed": "hors_ligne"}


@dataclass(frozen=True)
class SourcesCatalogue:
    """Emplacements lus ; les tests en passent d'autres."""

    verrou: Path = Path("/opt/acp/catalogue/catalogue.lock.json")
    greffons: Path = Path("/opt/hermes/plugins")


def lire_verrou(chemin: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """(verrou, SHA-256 du fichier) ; (None, None) s'il est illisible."""
    try:
        brut = chemin.read_bytes()
        verrou = json.loads(brut.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None, None
    if not isinstance(verrou, dict) or verrou.get("schema") != "acp-catalogue/1":
        return None, None
    return verrou, hashlib.sha256(brut).hexdigest()


def vue_du_chargeur() -> Dict[str, Any]:
    """Ce que le chargeur de skills de Hermes voit dans CE processus : dossiers externes, skills
    désactivées, et emplacements de chaque skill (dossier local du volume et dossiers externes),
    filtrés par plateforme comme le fait Hermes (tools/skills_tool.py, _find_all_skills)."""
    from agent.skill_utils import (get_disabled_skill_names, get_external_skills_dirs, iter_skill_index_files,
                                   parse_frontmatter, skill_matches_platform)
    from hermes_cli.config import read_raw_config
    from hermes_constants import get_skills_dir

    externes = [p for p in get_external_skills_dirs()]
    local = get_skills_dir()
    emplacements: Dict[str, List[str]] = {}
    for racine in [local, *externes]:
        if not racine.is_dir():
            continue
        for skill_md in iter_skill_index_files(racine, "SKILL.md"):
            try:
                entete, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8")[:4000])
            except (OSError, UnicodeDecodeError):
                continue
            if not skill_matches_platform(entete):
                continue
            nom = str(entete.get("name", skill_md.parent.name))[:64]
            emplacements.setdefault(nom, []).append(str(skill_md.parent))
    serveurs_bruts = (read_raw_config() or {}).get("mcp_servers")
    return {
        "external_dirs": [str(p) for p in externes],
        "dossier_local": str(local),
        "desactivees": sorted(get_disabled_skill_names()),
        "emplacements": emplacements,
        # Serveurs MCP déclarés dans la config BRUTE du volume : le tableau de bord ne lance sa
        # découverte MCP que s'il y en a un (hermes_cli/mcp_startup.py:53-65).
        "mcp_volume": sorted(serveurs_bruts) if isinstance(serveurs_bruts, dict) else [],
    }


def etat_mcp() -> Dict[str, Dict[str, Any]]:
    """État des serveurs MCP configurés, lu dans l'état en mémoire du client MCP de CE processus,
    sans jamais se connecter (tools/mcp_tool_discovery.py:672-720)."""
    from tools.mcp_tool_config import _load_mcp_config
    from tools.mcp_tool_discovery import get_mcp_status

    configures = _load_mcp_config()
    etats: Dict[str, Dict[str, Any]] = {}
    for entree in get_mcp_status(configures):
        nom = str(entree.get("name"))
        conf = configures.get(nom) or {}
        etats[nom] = {
            "statut_hermes": entree.get("status"),
            "connexion": ETATS_CONNEXION.get(str(entree.get("status")), "inconnu"),
            "outils": entree.get("tools"),
            "transport": entree.get("transport"),
            "url": conf.get("url") if isinstance(conf, dict) else None,
            "commande": bool(isinstance(conf, dict) and conf.get("command")),
        }
    return etats


def _version_manifeste(chemin: Path) -> Optional[str]:
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    version = donnees.get("version") if isinstance(donnees, dict) else None
    return str(version) if version else None


def bloc_interface(sources: SourcesCatalogue = SourcesCatalogue()) -> Dict[str, Any]:
    """Versions des greffons d'interface livrés et SDK du tableau de bord attendu (le contrôle du
    SDK lui-même se fait dans le navigateur, par les greffons)."""
    return {
        "greffons": {nom: _version_manifeste(sources.greffons / nom / "dashboard" / "manifest.json")
                     for nom in ("acp-interface", "acp-catalogue")},
        "sdk_attendu": SDK_ATTENDU,
    }


def construire_catalogue(sources: SourcesCatalogue = SourcesCatalogue(),
                         vue: Optional[Mapping[str, Any]] = None,
                         mcp: Optional[Mapping[str, Mapping[str, Any]]] = None) -> Dict[str, Any]:
    """Contenu de ``/v1/catalogue`` : le verrou et l'état de chaque entrée tel que Hermes le voit.

    ``vue`` et ``mcp`` remplacent la lecture dans Hermes (tests). États d'une skill côté Hermes :
    ``active``, ``desactivee``, ``absente`` (introuvable par le chargeur), ``ambigue`` (même nom à
    plusieurs emplacements : skill_view refuse un nom ambigu, tools/skills_tool.py:515-535) ;
    côté poste : l'état du verrou (``candidate-poste`` ; pour un MCP, ``reporte-p8`` ou ``hors-v1``)."""
    alertes: List[str] = []
    verrou, empreinte = lire_verrou(sources.verrou)
    if verrou is None:
        return {"verrou": {"sha256": None, "schema": None}, "sources": {}, "skills": [], "mcp": [], "profils": {},
                "hors_catalogue": [], "collisions": [], "desactivations_non_appliquees": [],
                "alertes": [f"Verrou du catalogue illisible : {sources.verrou}. Le catalogue d'ACP est inconnu."]}
    if vue is None:
        try:
            vue = vue_du_chargeur()
        except Exception as exc:  # noqa: BLE001 — état inconnu plutôt qu'une erreur 500
            vue = None
            alertes.append(f"État du chargeur de skills de Hermes illisible ({type(exc).__name__}) : états inconnus.")
    if mcp is None:
        try:
            mcp = etat_mcp()
        except Exception as exc:  # noqa: BLE001
            mcp = None
            alertes.append(f"État du client MCP de Hermes illisible ({type(exc).__name__}) : connexion inconnue.")

    racine = str(verrou.get("racine_image") or "")
    livrees = verrou.get("livrees") or {}
    noms_livres = set(livrees.get("noms") or [])
    requises = [str(e.get("nom")) for e in livrees.get("desactivees_par_acp") or [] if isinstance(e, dict)]
    skills: List[Dict[str, Any]] = []
    collisions: List[Dict[str, Any]] = []
    non_appliquees: List[str] = []
    hors_catalogue: List[str] = []
    external_dirs_conforme: Optional[bool] = None
    desactivations_conformes: Optional[bool] = None
    noms_catalogue = {str(s.get("nom")) for s in verrou.get("skills") or [] if isinstance(s, dict)}

    if vue is not None:
        externes = [str(Path(p)) for p in vue.get("external_dirs") or []]
        external_dirs_conforme = racine in externes
        if not external_dirs_conforme:
            alertes.append(f"skills.external_dirs ne contient pas {racine} : les skills du catalogue d'ACP ne sont "
                           "pas chargées (elles le seront au prochain démarrage, qui rétablit la liste).")
        desactivees = set(vue.get("desactivees") or [])
        non_appliquees = [n for n in requises if n not in desactivees]
        desactivations_conformes = not non_appliquees
        if non_appliquees:
            alertes.append(f"{len(non_appliquees)} skill(s) livrée(s) par Hermes que le catalogue désactive sont "
                           "actives (" + ", ".join(non_appliquees[:10]) + ("…" if len(non_appliquees) > 10 else "")
                           + ") : elles exigent un outil fermé sur Railway ; rétablies au prochain démarrage.")
        emplacements: Mapping[str, List[str]] = vue.get("emplacements") or {}
        for nom, lieux in sorted(emplacements.items()):
            if len(lieux) > 1:
                collisions.append({"nom": nom, "emplacements": list(lieux)})
            if nom not in noms_catalogue and nom not in noms_livres:
                hors_catalogue.append(nom)
        if collisions:
            alertes.append("Skills en collision (même nom à plusieurs emplacements, que Hermes refuse de charger) : "
                           + ", ".join(c["nom"] for c in collisions) + ".")
    for entree in verrou.get("skills") or []:
        if not isinstance(entree, dict):
            continue
        sortie = {k: entree.get(k) for k in ("nom", "source", "chemin_amont", "cible", "profils", "description_fr",
                                             "raison")}
        if entree.get("cible") != "hermes":
            sortie["etat"] = entree.get("etat")
        elif vue is None:
            sortie["etat"] = "inconnu"
        else:
            nom = str(entree.get("nom"))
            lieux = (vue.get("emplacements") or {}).get(nom) or []
            attendu = str(Path(racine) / str(entree.get("chemin")))
            if len(lieux) > 1:
                sortie["etat"] = "ambigue"
            elif nom in set(vue.get("desactivees") or []):
                sortie["etat"] = "desactivee"
            elif lieux == [attendu]:
                sortie["etat"] = "active"
            else:
                sortie["etat"] = "absente"
            sortie["emplacements"] = list(lieux)
        skills.append(sortie)
    absentes = [s["nom"] for s in skills if s.get("etat") == "absente"]
    if absentes and external_dirs_conforme:
        alertes.append("Skills du catalogue introuvables par le chargeur de Hermes : " + ", ".join(absentes) + ".")
    serveurs: List[Dict[str, Any]] = []
    for entree in verrou.get("mcp") or []:
        if not isinstance(entree, dict):
            continue
        sortie = {k: entree.get(k) for k in ("nom", "cible", "etat", "transport", "url", "outils_hermes", "profils",
                                             "description_fr", "raison")}
        if entree.get("cible") == "hermes":
            if vue is not None and vue.get("mcp_volume") is not None and entree.get("nom") not in vue["mcp_volume"]:
                alertes.append(f"Le serveur MCP {entree.get('nom')} n'est pas déclaré dans le config.yaml du volume : "
                               "la discussion du tableau de bord ne s'y connectera pas (rétabli au prochain démarrage).")
            etat = (mcp or {}).get(str(entree.get("nom"))) if mcp is not None else None
            if mcp is None:
                sortie["connexion"] = "inconnu"
            elif etat is None:
                sortie["connexion"] = "inconnu"
                alertes.append(f"Le serveur MCP {entree.get('nom')} du catalogue n'est pas configuré dans Hermes.")
            else:
                sortie["connexion"] = etat.get("connexion", "inconnu")
                sortie["statut_hermes"] = etat.get("statut_hermes")
                sortie["outils_exposes"] = etat.get("outils")
                if etat.get("url") != entree.get("url"):
                    alertes.append(f"Le serveur MCP {entree.get('nom')} ne pointe pas vers l'URL du catalogue.")
        serveurs.append(sortie)
    if mcp is not None:
        admis = {str(m.get("nom")) for m in verrou.get("mcp") or [] if isinstance(m, dict) and m.get("cible") == "hermes"}
        for nom in sorted(set(mcp) - admis):
            # Ajouté par la page MCP native (INSTALL, ADD SERVER) ou à la main : D8 refusera le prochain
            # démarrage ; le remède est de le SUPPRIMER depuis la même page (relecture de P3).
            alertes.append(f"Serveur MCP hors catalogue configuré dans Hermes : {nom}. Le prochain démarrage sera "
                           "refusé tant qu'il reste dans la configuration du volume : supprimez-le depuis la page "
                           "MCP du tableau de bord avant tout redémarrage (le désactiver ne suffit pas).")
    return {
        "verrou": {"sha256": empreinte, "schema": verrou.get("schema"), "hermes": verrou.get("hermes")},
        "racine_skills": racine,
        "sources": {k: {c: v.get(c) for c in ("url", "commit", "etiquette", "licence", "auteur", "categorie")}
                    for k, v in (verrou.get("sources") or {}).items() if isinstance(v, dict)},
        "skills": skills,
        "mcp": serveurs,
        "profils": verrou.get("profils") or {},
        "livrees": {
            "desactivees_par_acp": livrees.get("desactivees_par_acp") or [],
            "gardees": livrees.get("gardees") or [],
            "macos_seulement": livrees.get("macos_seulement") or [],
        },
        "exclus": verrou.get("exclus") or [],
        "external_dirs": list((vue or {}).get("external_dirs") or []) if vue is not None else None,
        "external_dirs_conforme": external_dirs_conforme,
        "desactivations_conformes": desactivations_conformes,
        "hors_catalogue": hors_catalogue,
        "collisions": collisions,
        "desactivations_non_appliquees": non_appliquees,
        "alertes": alertes,
    }


def resume_pour_meta(catalogue: Mapping[str, Any]) -> Dict[str, Any]:
    """Bloc ``catalogue`` de ``/v1/meta`` (contrat attendu par l'Accueil : docs/refonte/interface.md § 6)."""
    skills = [s for s in catalogue.get("skills") or [] if s.get("cible") == "hermes"]
    context7 = next((m for m in catalogue.get("mcp") or [] if m.get("nom") == "context7"), None)
    ecarts = (len(catalogue.get("collisions") or []) + len(catalogue.get("desactivations_non_appliquees") or [])
              + sum(1 for s in skills if s.get("etat") in ("absente", "ambigue"))
              + (1 if catalogue.get("external_dirs_conforme") is False else 0))
    inconnu = any(s.get("etat") == "inconnu" for s in skills)
    return {
        "verrou_sha256": (catalogue.get("verrou") or {}).get("sha256"),
        "skills_actives": None if inconnu or not catalogue.get("verrou", {}).get("sha256")
        else sum(1 for s in skills if s.get("etat") == "active"),
        "skills_attendues": len(skills) if (catalogue.get("verrou") or {}).get("sha256") else None,
        "context7": (context7 or {}).get("connexion", "inconnu") if context7 is not None else "inconnu",
        "external_dirs_conforme": catalogue.get("external_dirs_conforme"),
        "desactivations_conformes": catalogue.get("desactivations_conformes"),
        "ecarts": ecarts,
    }
