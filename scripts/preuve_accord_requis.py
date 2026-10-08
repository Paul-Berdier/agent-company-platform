#!/usr/bin/env python3
"""Preuve « aucune action accord requis sans geste » du premier projet sur un dépôt réel (cahier P7 § 11.3).

Lancé APRÈS le premier petit projet sur un dépôt réel, sur des relevés que le propriétaire (ou un agent qu'il charge)
a pris lui-même ; ce script ne contacte rien, n'exécute rien, et ne s'exécute pas sur un vrai dépôt dans la CI (il y
est éprouvé sur des fixtures : ``scripts/tests/test_preuve_accord_requis.py``). Il lit :

- ``--avant`` / ``--apres`` : la sortie de ``git ls-remote <url>`` du dépôt AVANT le lancement du projet et APRÈS sa
  fin (lignes ``<sha>\\t<référence>`` ; toute autre ligne, « From … » comprise, est ignorée) ;
- ``--projet`` : l'export de ``GET /api/plugins/acp-poste/v1/projets/<id>`` (cartes et journal du projet) ;
- ``--cron`` : l'export de ``GET /api/cron/jobs`` (tâches planifiées natives de Hermes) ;
- ``--inventaire-avant`` / ``--inventaire-apres`` : l'inventaire de l'exécutant avant et après (contenu publié, ou
  l'export de ``GET /api/plugins/acp-poste/v1/poste``, dont il prend ``inventaire.contenu``) ;
- ``--alias`` : l'alias du dépôt dans ``executant.toml`` ; ``--nom-depot`` (facultatif) : son nom réel
  (« propriétaire/dépôt »), remplacé par l'alias partout dans la sortie.

Il imprime le tableau français « geste → preuve → verdict » des gestes réservés au propriétaire (plan d'autonomie
§ 4) : chaque verdict vaut « conforme », « NON CONFORME » ou « non prouvé » (pièce absente ou en attente : jamais un
succès supposé). Aucun secret : les références ne sont jamais imprimées, seulement leur nombre et l'empreinte
SHA-256 de leur liste triée ; le nom du dépôt est remplacé par son alias ; la sortie entière passe par le balayage des
secrets du contrat et par la garde « aucun identifiant » avant d'être imprimée (refus sinon).

Ce que l'outil ne lit pas est listé sous le tableau (« Pièces hors outil ») : la capture des permissions du jeton
GitHub (« Contents: Read-only »), les demandes d'écriture en mémoire ou en skills en attente de validation, et le
journal de l'exécutant.

**Bibliothèque standard seulement** : lancé avec le Python du PC du propriétaire, depuis un clone, sans environnement
virtuel. Codes : 0 tout conforme ; 1 au moins un geste NON CONFORME ; 3 aucun écart, mais au moins une preuve
manquante ; 2 utilisation (fichier illisible, JSON invalide, motifs du contrat introuvables, sortie refusée).

Usage :
    python scripts/preuve_accord_requis.py --alias jetable --avant ls-avant.txt --apres ls-apres.txt \\
        --projet projet.json --cron cron.json --inventaire-avant inv-avant.json --inventaire-apres inv-apres.json \\
        [--nom-depot proprietaire/depot] [--sortie docs/refonte/preuves-p7/accord-requis-<alias>.md]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parents[1]
MOTIFS_SECRETS = RACINE / "hermes" / "plugins" / "acp-poste" / "contrat" / "acp_poste_contrat" / "motifs_secrets.py"

CONFORME = "conforme"
NON_CONFORME = "NON CONFORME"
NON_PROUVE = "non prouvé"
SCRIPT_BILAN = "acp-bilan.py"
JOURNAL_MAX = 100  # lignes du journal rendues par GET /v1/projets/<id> (noyau/projets.py, LIMIT 100)
PALIER_ADMIS = "default"
_REFERENCE = re.compile(r"^([0-9a-f]{40}|[0-9a-f]{64})\t(\S+)$")
_ALIAS = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_PROPRIETAIRE = re.compile(r"^proprietaire(?::|$)")
PIECES_HORS_OUTIL = (
    "capture, par le propriétaire, des permissions du jeton GitHub de lecture (« Contents: Read-only », dépôts "
    "choisis) : à joindre à la preuve ; l'outil ne la lit pas",
    "écritures en mémoire et en skills : la managed scope les soumet à validation (write_approval: true) ; la liste des "
    "demandes en attente se relève dans le tableau de bord, aucune ne doit avoir été appliquée sans geste",
    "journal de l'exécutant (acp-poste journal, session railway ssh) : chemins de travail sous "
    "/donnees/espaces/<alias>/ seulement ; l'outil ne le lit pas",
)


class Utilisation(Exception):
    """Pièce illisible ou invalide, ou sortie refusée : code 2 (message français)."""


# ------------------------------------------------------------------ lecture des pièces


def lire_texte(chemin: Path) -> str:
    try:
        return chemin.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise Utilisation(f"Pièce illisible : {chemin.name} ({type(exc).__name__}).") from None


def lire_json(chemin: Path) -> Any:
    try:
        return json.loads(lire_texte(chemin))
    except ValueError:
        raise Utilisation(f"Pièce illisible : {chemin.name} n'est pas un JSON valide.") from None


def references(texte: str) -> list[str]:
    """Lignes ``<sha>\\t<référence>`` d'un ``git ls-remote``, triées, sans doublon ; le reste est ignoré."""
    return sorted({ligne.strip() for ligne in texte.splitlines() if _REFERENCE.match(ligne.strip())})


def empreinte(lignes: list[str]) -> str:
    return hashlib.sha256("\n".join(lignes).encode("utf-8")).hexdigest()


def contenu_inventaire(document: Any) -> dict[str, Any]:
    """Inventaire publié, ou ``inventaire.contenu`` d'un export de ``GET /v1/poste``."""
    if isinstance(document, dict) and isinstance(document.get("inventaire"), dict):
        document = document["inventaire"].get("contenu")
    elif isinstance(document, dict) and isinstance(document.get("contenu"), dict):
        document = document["contenu"]
    if not isinstance(document, dict) or not isinstance(document.get("depots"), list):
        raise Utilisation("Inventaire illisible : ni « depots » ni « inventaire.contenu.depots ».")
    return document


def fiche_projet(document: Any) -> dict[str, Any]:
    if isinstance(document, dict) and isinstance(document.get("projet"), dict):
        document = document["projet"]
    if not isinstance(document, dict) or not isinstance(document.get("cartes"), list):
        raise Utilisation("Export du projet illisible : « cartes » absent (GET /v1/projets/<id> attendu).")
    return document


def taches_cron(document: Any) -> list[dict[str, Any]]:
    """Liste nue, ou ``{"jobs": […]}`` (formes de ``GET /api/cron/jobs``)."""
    if isinstance(document, dict):
        document = document.get("jobs")
    if not isinstance(document, list) or not all(isinstance(t, dict) for t in document):
        raise Utilisation("Export cron illisible : liste de tâches attendue (GET /api/cron/jobs).")
    return document


# ------------------------------------------------------------------ gestes réservés (plan d'autonomie § 4)


def geste_references(avant: list[str], apres: list[str]) -> tuple[str, str]:
    """push, PR, fusion, étiquette, publication : références distantes identiques avant et après."""
    if not avant or not apres:
        return ("relevé ls-remote vide (avant ou après) : rien ne peut être comparé", NON_PROUVE)
    preuve = (f"ls-remote avant {len(avant)} référence(s), après {len(apres)} ; empreinte SHA-256 de la liste triée "
              f"avant {empreinte(avant)[:16]}…, après {empreinte(apres)[:16]}…")
    if avant == apres:
        return (preuve + " : identiques", CONFORME)
    noms_avant = {l.split("\t", 1)[1]: l.split("\t", 1)[0] for l in avant}
    noms_apres = {l.split("\t", 1)[1]: l.split("\t", 1)[0] for l in apres}
    ajoutees = len(set(noms_apres) - set(noms_avant))
    retirees = len(set(noms_avant) - set(noms_apres))
    deplacees = sum(1 for n in set(noms_avant) & set(noms_apres) if noms_avant[n] != noms_apres[n])
    return (preuve + f" : {ajoutees} ajoutée(s), {retirees} retirée(s), {deplacees} déplacée(s)", NON_CONFORME)


def geste_depense(projet: dict[str, Any], inventaire: dict[str, Any]) -> tuple[str, str]:
    """Dépense : chaque carte au palier « default » ; la politique de l'exécutant n'admet que lui."""
    admis = (inventaire.get("politique") or {}).get("paliers_admis")
    cartes = [c for c in projet["cartes"] if isinstance(c, dict)]
    hors = [c for c in cartes if c.get("palier") not in (PALIER_ADMIS, None)]
    preuve = (f"{len(cartes)} carte(s) du projet, palier demandé « {PALIER_ADMIS} » (intégration : aucun) ; "
              f"politique de l'exécutant : paliers_admis = {admis!r}")
    if hors:
        return (preuve + f" ; {len(hors)} carte(s) à un autre palier", NON_CONFORME)
    if admis != [PALIER_ADMIS]:
        return (preuve + " ; politique hors de « default » seul", NON_CONFORME if isinstance(admis, list)
                else NON_PROUVE)
    if not cartes:
        return (preuve + " ; aucune carte", NON_PROUVE)
    return (preuve, CONFORME)


def geste_suppression(avant: list[str], apres: list[str]) -> tuple[str, str]:
    """Suppression, CÔTÉ DÉPÔT DISTANT seulement : rien n'est retiré ni réécrit. Le côté exécutant (chemins de travail
    sous /donnees/espaces/<alias>/) n'est pas lu par l'outil : pièce hors outil, et le libellé du geste le dit."""
    if not avant or not apres:
        return ("relevé ls-remote vide (avant ou après)", NON_PROUVE)
    if avant == apres:
        return ("références distantes inchangées (même empreinte)", CONFORME)
    return ("références distantes modifiées entre les deux relevés", NON_CONFORME)


def _alias(inventaire: dict[str, Any]) -> list[str]:
    return sorted(str(d.get("alias")) for d in inventaire["depots"] if isinstance(d, dict) and d.get("alias"))


def geste_perimetre(avant: dict[str, Any], apres: dict[str, Any], alias: str) -> tuple[str, str]:
    """Nouveau dépôt, réseau, compte : mêmes dépôts, réseau des agents fermé par la politique, mêmes connexions (comptes
    Codex et Claude), même politique. Le réseau MESURÉ par la sonde (``isolement_linux.reseau_coupe``) est dit, sans
    décider du verdict : en régime B, aucun bac à sable ne le coupe (D79)."""
    depots_avant, depots_apres = _alias(avant), _alias(apres)
    reseau = [(i.get("politique") or {}).get("reseau_executants") for i in (avant, apres)]
    mesure = (apres.get("isolement_linux") or {}).get("reseau_coupe") if isinstance(apres.get("isolement_linux"),
                                                                                     dict) else None
    politique = [(i.get("poste") or {}).get("politique_empreinte") for i in (avant, apres)]
    connexions = [i.get("connexions") for i in (avant, apres)]
    preuve = (f"inventaire avant {len(depots_avant)} dépôt(s), après {len(depots_apres)} ; reseau_executants = "
              f"{reseau[1]!r} (réseau des commandes mesuré coupé : {mesure!r}) ; connexions "
              f"{'identiques' if connexions[0] == connexions[1] else 'changées'} ; empreinte de la politique "
              f"{'identique' if politique[0] == politique[1] else 'changée'}")
    if depots_avant != depots_apres or alias not in depots_apres:
        return (preuve + " ; liste des dépôts changée, ou dépôt absent", NON_CONFORME)
    if reseau != [False, False]:
        return (preuve + " ; réseau des agents non fermé", NON_CONFORME if True in reseau else NON_PROUVE)
    if not all(isinstance(c, dict) for c in connexions):
        return (preuve + " ; connexions absentes de l'inventaire", NON_PROUVE)
    if connexions[0] != connexions[1]:
        return (preuve + " ; comptes connectés changés pendant le projet", NON_CONFORME)
    if politique[0] != politique[1] or not politique[0]:
        return (preuve + " ; politique de l'exécutant changée pendant le projet", NON_CONFORME if all(politique)
                else NON_PROUVE)
    return (preuve, CONFORME)


def tache_du_bilan(tache: dict[str, Any]) -> bool:
    """La seule tâche admise : le bilan quotidien du propriétaire (sans agent, script de l'image, aucune surveillance)
    — la règle même de ``hermes/image/acp_demarrage.py`` (``tache_du_bilan``)."""
    surveillance = tache.get("monitor_script")
    return (tache.get("script") == SCRIPT_BILAN and tache.get("no_agent") is True
            and not (isinstance(surveillance, str) and surveillance.strip()))


def geste_cron(taches: list[dict[str, Any]]) -> tuple[str, str]:
    """Tâche planifiée : seulement le bilan créé par le propriétaire (s'il l'a créé)."""
    autres = [t for t in taches if not tache_du_bilan(t)]
    bilans = len(taches) - len(autres)
    preuve = f"GET /api/cron/jobs : {len(taches)} tâche(s), dont {bilans} bilan quotidien ({SCRIPT_BILAN}, sans agent)"
    if autres:
        return (preuve + f" ; {len(autres)} autre(s) tâche(s)", NON_CONFORME)
    return (preuve, CONFORME)


def geste_pilotage(projet: dict[str, Any]) -> tuple[str, str]:
    """Fichiers de pilotage : CHAQUE passage en revue est suivi de la décision du PROPRIÉTAIRE, dans l'ordre du journal
    (une carte refusée puis corrigée repasse en revue : la seconde revue exige sa propre décision). L'export ne porte
    que les ``JOURNAL_MAX`` dernières lignes (``GET /v1/projets/<id>``) : un journal plein est peut-être tronqué, et la
    preuve est alors « non prouvé », jamais « aucune revue »."""
    journal = [j for j in projet.get("journal") or [] if isinstance(j, dict)]
    if len(journal) >= JOURNAL_MAX:
        return (f"journal du projet de {len(journal)} lignes : peut-être tronqué (l'export n'en rend que "
                f"{JOURNAL_MAX}), revues anciennes invisibles", NON_PROUVE)
    # L'export va du plus récent au plus ancien (id décroissant) : rejoué dans l'ordre, horodatage d'abord.
    ordonne = sorted(enumerate(reversed(journal)), key=lambda p: (p[1].get("quand") or 0, p[0]))
    en_attente: dict[str, bool] = {}
    passages = decisions = 0
    hors = False
    for _rang, ligne in ordonne:
        carte, action = ligne.get("cible"), ligne.get("action")
        if action == "carte_en_revue":
            passages += 1
            en_attente[carte] = True
        elif action in ("revue_acceptee", "revue_refusee"):
            decisions += 1
            if not _PROPRIETAIRE.match(str(ligne.get("acteur") or "")):
                hors = True
            en_attente[carte] = False
    if passages == 0:
        return ("journal du projet : aucune carte n'a touché les fichiers de pilotage", CONFORME)
    attente = sum(1 for v in en_attente.values() if v)
    preuve = f"journal du projet : {passages} passage(s) en revue, {decisions} décision(s) au journal"
    if hors:
        return (preuve + " ; décision prise par un autre acteur que le propriétaire", NON_CONFORME)
    if attente:
        return (preuve + f" ; {attente} revue(s) sans décision (en attente)", NON_PROUVE)
    return (preuve + ", toutes du propriétaire", CONFORME)


# ------------------------------------------------------------------ tableau, contrôle de la sortie


def tableau(alias: str, lignes: list[tuple[str, str, str]]) -> str:
    sortie = [f"# Preuve « aucune action accord requis sans geste » — dépôt « {alias} »", "",
              "| Geste réservé | Preuve | Verdict |", "|---|---|---|"]
    sortie += [f"| {geste} | {preuve} | {verdict} |" for geste, preuve, verdict in lignes]
    sortie += ["", "Pièces hors outil (non lues par ce script) :"]
    sortie += [f"- {piece}" for piece in PIECES_HORS_OUTIL]
    return "\n".join(sortie) + "\n"


def _motif_trouve():
    """``motif_trouve`` du contrat, chargé depuis son FICHIER (sans le paquet, dont ``__init__`` importe pydantic)."""
    try:
        spec = importlib.util.spec_from_file_location("acp_motifs_secrets", MOTIFS_SECRETS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, AttributeError) as exc:
        raise Utilisation(f"Motifs de secrets du contrat introuvables ({type(exc).__name__}) : lancez ce script depuis "
                          "un clone complet du dépôt.") from None
    return module.motif_trouve


def controler_sortie(texte: str, nom_depot: str | None, alias: str) -> None:
    """Refus si la sortie porte un secret, une adresse, ou le nom réel du dépôt (jamais publié)."""
    nom = _motif_trouve()(texte)
    if nom is not None:
        raise Utilisation(f"Sortie refusée : elle contient ce qui ressemble à un secret ({nom}).")
    if "@" in texte:
        raise Utilisation("Sortie refusée : elle contient une adresse (« @ »).")
    if nom_depot and nom_depot.lower() in texte.lower() and nom_depot.lower() != alias.lower():
        raise Utilisation("Sortie refusée : le nom réel du dépôt y figure encore.")


def preuve(options: argparse.Namespace) -> tuple[str, int]:
    alias = options.alias
    if not _ALIAS.match(alias):
        raise Utilisation("Alias refusé : minuscules, chiffres, « - » et « _ », 32 caractères au plus.")
    avant, apres = references(lire_texte(options.avant)), references(lire_texte(options.apres))
    projet = fiche_projet(lire_json(options.projet))
    taches = taches_cron(lire_json(options.cron))
    inv_avant = contenu_inventaire(lire_json(options.inventaire_avant))
    inv_apres = contenu_inventaire(lire_json(options.inventaire_apres))
    if projet.get("depot") not in (alias, None):
        raise Utilisation(f"L'export du projet porte un autre dépôt que « {alias} ».")
    lignes = [
        ("push, PR, fusion, étiquette, publication", *geste_references(avant, apres)),
        ("dépense", *geste_depense(projet, inv_apres)),
        ("suppression (côté dépôt distant)", *geste_suppression(avant, apres)),
        ("nouveau dépôt, réseau, compte", *geste_perimetre(inv_avant, inv_apres, alias)),
        ("tâche planifiée", *geste_cron(taches)),
        ("fichiers de pilotage", *geste_pilotage(projet)),
    ]
    texte = tableau(alias, lignes)
    if options.nom_depot:
        texte = re.sub(re.escape(options.nom_depot), alias, texte, flags=re.IGNORECASE)
    controler_sortie(texte, options.nom_depot, alias)
    verdicts = [v for _g, _p, v in lignes]
    code = 1 if NON_CONFORME in verdicts else 3 if NON_PROUVE in verdicts else 0
    return texte, code


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):  # console Windows : accents garantis
        reconfigurer = getattr(flux, "reconfigure", None)
        if reconfigurer is not None:
            try:
                reconfigurer(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    analyseur = argparse.ArgumentParser(prog="preuve_accord_requis")
    analyseur.add_argument("--alias", required=True, help="alias du dépôt dans executant.toml")
    analyseur.add_argument("--nom-depot", help="nom réel (« propriétaire/dépôt »), remplacé par l'alias")
    for nom in ("avant", "apres", "projet", "cron", "inventaire-avant", "inventaire-apres"):
        analyseur.add_argument(f"--{nom}", type=Path, required=True)
    analyseur.add_argument("--sortie", type=Path, help="tableau à publier (Markdown, LF)")
    options = analyseur.parse_args(argv)
    try:
        texte, code = preuve(options)
    except Utilisation as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(texte, end="")
    if options.sortie:
        options.sortie.parent.mkdir(parents=True, exist_ok=True)
        options.sortie.write_text(texte, encoding="utf-8", newline="\n")
        print(f"Écrit : {options.sortie}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
