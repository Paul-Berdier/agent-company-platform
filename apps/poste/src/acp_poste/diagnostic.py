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

Exécutant Linux (étape P6) : bloc ``executant`` — verdict de la sonde de plateforme du démarrage, état de
l'exécution (``peut_executer`` et sa raison, voies, carte en main), file de sortie (en attente, refusées), pause
locale, espace libre du volume, plafonds du jour, jeton GitHub de lecture (présence seulement) ; ``--isolement`` y
ajoute le nombre de sockets à l'écoute lu dans ``/proc/net/tcp`` et ``/proc/net/tcp6`` (état ``0A`` ; preuve R1 :
l'exécutant n'écoute aucun port), ``ss`` n'étant pas dans l'image.
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


def sockets_a_l_ecoute(racine: Path = Path("/proc/net")) -> int | None:
    """Nombre de sockets TCP à l'écoute (état ``0A``) d'après ``/proc/net/tcp`` et ``tcp6`` ; ``None`` si illisible."""
    total, lu = 0, False
    for nom in ("tcp", "tcp6"):
        try:
            lignes = (racine / nom).read_text(encoding="ascii", errors="replace").splitlines()[1:]
        except OSError:
            continue
        lu = True
        total += sum(1 for ligne in lignes if len(ligne.split()) > 3 and ligne.split()[3] == "0A")
    return total if lu else None


def _executant(contexte: Contexte, politique: Politique | None, isolement: bool) -> dict[str, Any]:
    from .depots import espace_libre_mio
    from .garde_quota import Budget
    from .sortie import FileSortie

    e = contexte.emplacements
    sonde = _lire_json(e.sonde_isolement) or {}
    verdict = sonde.get("verdict") or {}
    etat = (_lire_json(e.etat_service) or {}).get("execution") or {}
    en_main = _lire_json(e.carte) or {}
    file = FileSortie(e.sortie, e.sortie_refusees)
    try:
        refusees = len([f for f in e.sortie_refusees.iterdir() if f.suffix == ".json"])
    except OSError:
        refusees = 0
    try:
        github = contexte.coffre.present("jeton-github")
    except CoffreErreur:
        github = None
    budget = None
    if politique is not None:
        jour = Budget(e.compteurs, politique.politique.cartes_par_jour,
                      politique.politique.heures_agent_par_jour).etat()
        budget = {"cartes": jour["cartes"], "cartes_max": politique.politique.cartes_par_jour,
                  "heures_agent": round(jour["secondes_agent"] / 3600, 2),
                  "heures_max": politique.politique.heures_agent_par_jour}
    return {
        "sonde": {"regime": verdict.get("regime", "inconnu"), "bwrap": verdict.get("bwrap"),
                  "uid_separes": verdict.get("uid_separes"), "raison": verdict.get("raison"),
                  "sonde_le": sonde.get("sonde_le")} if verdict else None,
        "execution": {"peut_executer": etat.get("peut_executer"), "raison": etat.get("raison"),
                      "voies": etat.get("voies")} if etat else None,
        "carte_en_main": {"carte": en_main.get("carte"), "role": en_main.get("role"), "etape": en_main.get("etape")}
        if en_main else None,
        "file_de_sortie": {"en_attente": len(file.en_attente()), "refusees": refusees},
        "pause_locale": e.pause_locale.exists(),
        "espace_libre_mio": espace_libre_mio(e.donnees) if e.donnees.exists() else None,
        "plafonds_du_jour": budget,
        "jeton_github": "present" if github else ("absent" if github is False else "illisible"),
        "sockets_a_l_ecoute": sockets_a_l_ecoute() if isolement else None,
    }


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
            "profil": "present" if section.home.is_dir() else "absent",
            # Variante de la plateforme (Linux : stockage « file », sans réglage Windows) : sans elle, l'exécutant
            # affichait « modifie » pour le config.toml qu'il venait d'écrire (relevé dans l'image, 01/10/2026).
            "config_toml": etat_config_toml(section.home, politique.plateforme),
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
    linux = contexte.plateforme == "linux"
    rapport["service"] = {"verrou": "tenu" if est_tenu(emplacements.verrou_instance) else "libre",
                          "tache_planifiee": None if linux else _tache_planifiee()}
    rapport["isolement"] = _isolement(politique) if (isolement and politique is not None and not linux) else None
    if linux:
        rapport["executant"] = _executant(contexte, politique, isolement)
    trouve = identifiant_trouve(rapport)
    if trouve:  # garde : un diagnostic ne porte jamais de chemin ni d'identifiant
        rapport = {"version_poste": __version__, "erreur": f"Diagnostic retenu par la garde « aucun identifiant » "
                   f"({trouve.split(' : ')[0]})."}
    return rapport
