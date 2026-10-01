"""Diagnostic du poste (cahier P5 § 6.5) : un objet JSON **sans chemin ni secret**.

Il dit ce que le poste sait de lui-même : compte (mode, conformité), politique (valide, empreinte, modifiable par
le compte), jeton (présence, identifiant, empreinte courte), Hermes (dernier échange vu par le service, état du
poste, refus du jeton, écart d'horloge), Codex et Claude (exécutable, version lue et testée, profil, dernier relevé,
bac à sable, connexion), service (verrou tenu, tâche planifiée).

- ``--reseau`` : ``GET /api/health`` sans jeton (chemin public de Hermes) ; un échec TLS se dit en français.
- ``--isolement`` : tente de **lister** les dossiers de ``[isolement] profils_interdits`` et attend un refus d'accès
  (aucun fichier n'est ouvert, rien n'est lu) ; ``profil_proprietaire_lisible: false`` est la preuve attendue en
  compte dédié.

Aucune valeur n'est inventée : ce qui n'est pas su vaut ``null`` ou « inconnu ».
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from acp_poste_contrat.inventaire import PROTOCOLE, identifiant_trouve

from . import __version__
from .coffre import CoffreErreur
from .contexte import Contexte
from .enrolement import identite
from .politique import Politique, PolitiqueRefusee, charger, modifiable_par_le_poste
from .protocole import Protocole
from .sondes_claude import environnement_claude
from .sondes_codex import etat_config_toml, lire_version
from .subscription_quotas import codex_environment
from .verrou import est_tenu

LIGNE_ETAT_PERIMEE_S = 2 * 3600
TACHE = r"\ACP\Poste ACP"


def _lire_json(chemin: Path) -> dict[str, Any] | None:
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        return donnees if isinstance(donnees, dict) else None
    except (OSError, ValueError):
        return None


def _version(argv: list[str], env: dict[str, str]) -> str | None:
    try:
        with tempfile.TemporaryDirectory(prefix="acp-sonde-", ignore_cleanup_errors=True) as dossier:
            return asyncio.run(asyncio.wait_for(lire_version(argv, env, dossier), timeout=20))
    except Exception:  # noqa: BLE001 - « inconnue » plutôt qu'une trace
        return None


def _tache_planifiee() -> str:
    if os.name != "nt":
        return "inconnue"
    try:
        sortie = subprocess.run(["schtasks", "/Query", "/TN", TACHE, "/FO", "CSV", "/NH"], capture_output=True,
                                timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "inconnue"
    if sortie.returncode != 0:
        return "absente"
    # schtasks écrit dans la page de code OEM de la console (cp850 sur un Windows français) ; états localisés.
    texte = sortie.stdout.decode("oem", "replace").lower()
    for motifs, etat in ((("running", "en cours"), "en_cours"), (("ready", "prêt"), "prete"),
                         (("disabled", "désactivé"), "desactivee")):
        if any(m in texte for m in motifs):
            return etat
    return "presente"


def _ligne_etat(chemin: Path | None) -> str:
    if chemin is None:
        return "non_declaree"
    try:
        age = datetime.now(UTC).timestamp() - chemin.stat().st_mtime
    except OSError:
        return "absente"
    return "perimee" if age > LIGNE_ETAT_PERIMEE_S else "fraiche"


def _isolement(politique: Politique) -> dict[str, Any]:
    lisibles = 0
    refuses = 0
    absents = 0
    for dossier in politique.profils_interdits:
        try:
            with os.scandir(dossier) as entrees:
                next(entrees, None)
            lisibles += 1
        except PermissionError:
            refuses += 1
        except FileNotFoundError:
            absents += 1
        except OSError:
            refuses += 1
    if not politique.profils_interdits:
        lisible = None
    else:
        lisible = lisibles > 0
    return {"profil_proprietaire_lisible": lisible, "profils": len(politique.profils_interdits),
            "refuses": refuses, "absents": absents}


def diagnostic(contexte: Contexte, *, reseau: bool = False, isolement: bool = False) -> dict[str, Any]:
    emplacements = contexte.emplacements
    rapport: dict[str, Any] = {"version_poste": __version__, "protocole": PROTOCOLE}
    politique: Politique | None = None
    try:
        politique = charger(emplacements)
        rapport["politique"] = {"etat": "valide", "empreinte": politique.empreinte,
                                "modifiable_par_le_poste": modifiable_par_le_poste(politique)}
    except PolitiqueRefusee as exc:
        rapport["politique"] = {"etat": "invalide", "empreinte": None, "modifiable_par_le_poste": None,
                                "refus": str(exc)[:300]}
    try:
        courant = contexte.compte_courant()
    except Exception:  # noqa: BLE001
        courant = None
    if politique is not None:
        conforme = (courant is not None and courant.casefold() == (politique.poste.compte_attendu or "").casefold()) \
            if politique.compte_dedie else True
        rapport["compte"] = {"mode": politique.poste.compte, "conforme": conforme}
    else:
        rapport["compte"] = {"mode": None, "conforme": None}

    machine = identite(contexte) or {}
    try:
        present = contexte.coffre.present("jeton-machine")
    except CoffreErreur:
        present = None
    rapport["jeton"] = {"present": present, "machine_id": machine.get("machine_id"),
                        "empreinte": machine.get("empreinte")}

    etat = _lire_json(emplacements.etat_service) or {}
    rapport["hermes"] = {"origine_https": politique.hermes.origine.startswith("https://") if politique else None,
                         "joignable": None, "dernier_echange": etat.get("dernier_echange"),
                         "etat_machine": etat.get("etat_machine"), "jeton_refuse_depuis": etat.get("jeton_refuse_depuis"),
                         "ecart_horloge_s": etat.get("ecart_horloge_s"),
                         "dernier_inventaire": etat.get("dernier_inventaire")}
    if reseau and politique is not None:
        joignable, message = Protocole(contexte.client(politique)).sante()
        rapport["hermes"]["joignable"] = joignable
        rapport["hermes"]["reseau"] = message

    inventaire = _lire_json(emplacements.dernier_inventaire) or {}
    releves = {r.get("voie"): r for r in inventaire.get("releves") or [] if isinstance(r, dict)}
    connexions = inventaire.get("connexions") or {}
    versions = inventaire.get("versions") or {}

    if politique is not None and politique.codex is not None:
        section = politique.codex
        lanceur = contexte.lanceurs.get("codex") or ([str(section.executable)] if section.executable.is_file() else None)
        lue = _version(lanceur, codex_environment(section.home, source=contexte.environnement)) if lanceur else None
        releve = releves.get("poste-codex") or {}
        rapport["codex"] = {
            "executable": "present" if lanceur else "absent", "version": lue, "version_testee": section.version_testee,
            "version_conforme": lue == section.version_testee if lue else None,
            "profil": "present" if section.home.is_dir() else "absent", "config_toml": etat_config_toml(section.home),
            "connexion": connexions.get("codex"), "dernier_releve": releve.get("releve_le"),
            "origine_liste": releve.get("origine_liste"), "etat_releve": releve.get("etat"),
            "bac_a_sable": {k: (inventaire.get("bac_a_sable_codex") or {}).get(k) for k in
                            ("readiness", "mode_lu", "origine_mode", "ecriture_admise", "raison")},
        }
    else:
        rapport["codex"] = None
    if politique is not None and politique.claude is not None:
        section = politique.claude
        lanceur = contexte.lanceurs.get("claude") or ([str(section.executable)] if section.executable.is_file() else None)
        lue = _version(lanceur, environnement_claude(section, source=contexte.environnement)) if lanceur else None
        try:
            jeton = contexte.coffre.present("jeton-claude")
        except CoffreErreur:
            jeton = None
        rapport["claude"] = {
            "executable": "present" if lanceur else "absent", "version": lue, "version_testee": section.version_testee,
            "version_conforme": lue == section.version_testee if lue else None,
            "jeton": "present" if jeton else ("absent" if jeton is False else "illisible"),
            "auth_status": connexions.get("claude"), "ligne_etat": _ligne_etat(section.ligne_etat),
            "dernier_releve": (releves.get("poste-claude") or {}).get("releve_le"),
        }
    else:
        rapport["claude"] = None
    rapport["versions_publiees"] = versions or None
    rapport["service"] = {"verrou": "tenu" if est_tenu(emplacements.verrou_instance) else "libre",
                          "tache_planifiee": _tache_planifiee()}
    rapport["isolement"] = _isolement(politique) if (isolement and politique is not None) else None
    trouve = identifiant_trouve(rapport)
    if trouve:  # garde : un diagnostic ne porte jamais de chemin ni d'identifiant
        rapport = {"version_poste": __version__, "erreur": f"Diagnostic retenu par la garde « aucun identifiant » "
                   f"({trouve.split(' : ')[0]})."}
    return rapport
