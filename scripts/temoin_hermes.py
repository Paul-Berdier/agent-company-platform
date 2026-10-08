#!/usr/bin/env python3
"""Témoin de montée de version de Hermes (cahier P9 § 5.5) : périmètre de l'écriture, sonde de démarrage et
tableau des écarts.

Lancé par le job « temoin » de .github/workflows/image.yml (workflow_dispatch, entrée ``temoin_etiquette``), dans
la copie de travail du runner où ``scripts/monter_hermes.py ecrire <étiquette>`` a réécrit les épingles fortes ;
jamais en local (plus aucune pile Docker sur le poste du propriétaire). Rien n'est committé ni poussé. Sous-commandes :

``perimetre``
    Fichiers modifiés ou ajoutés dans la copie de travail (``git status``) : code 0 s'ils sont tous des épingles
    fortes (``monter_hermes.EPINGLES_FORTES``), 1 sinon (défaut de l'outil : il a écrit hors de son périmètre).
``sonde --image IMAGE --prefixe PREFIXE [--variables-de JOURNAL] [--journal-conteneur FICHIER]``
    Démarre l'image d'ACP sur un volume neuf avec les variables valides des tests de contrat
    (``hermes/tests/contrat/conftest.py``, ``ENV_VALIDE``) et dit si elle démarre : tableau de bord ``/api/status``
    en 200, puis passerelle et ``api_server`` branchés. Code 0 si elle démarre, 1 sinon, 2 sur refus. Avec
    ``--variables-de`` (diagnostic, HORS VERDICT) : ajoute seulement les variables que la garde de démarrage a
    réclamées dans le journal donné (« la variable X manque ; l'image la fixe à « V » ») pour voir ce qui se cache
    derrière ce premier refus ; la borne ``requires_hermes`` du greffon n'est jamais touchée.
``tableau --etapes-env NOM --dossier DOSSIER --etiquette ETIQUETTE [--sortie FICHIER]``
    Tableau des écarts en Markdown : chaque contrôle (étape du job, lue dans ``toJSON(steps)``) et son résultat,
    le détail tiré de son journal, puis, pour chaque suite pytest (rapport JUnit), les compteurs, les raisons les
    plus fréquentes et chaque test en échec. Code 0 si tous les contrôles comptés ont réussi, 1 sinon (le job
    échoue : rien n'est passé sous silence), 2 si les données sont illisibles.

Bibliothèque standard seulement ; les commandes externes passent par un exécuteur injectable
(``scripts/tests/test_temoin_hermes.py`` n'appelle ni Docker ni git réel pour la sonde).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "scripts"))
import monter_hermes as mh  # noqa: E402  (même dossier : liste des épingles fortes, exécuteur et refus partagés)

Refus = mh.Refus
Resultat = mh.Resultat
Executeur = mh.Executeur

FORME_ETIQUETTE_TEMOIN = re.compile(r"v[0-9]{4}\.[0-9]{1,2}\.[0-9]{1,2}", re.ASCII)

# Variables valides des tests de contrat (hermes/tests/contrat/conftest.py, ENV_VALIDE) : émetteur et URL publique
# factices, jamais joints par la sonde.
ENV_SONDE: Dict[str, str] = {
    "HERMES_DASHBOARD_PUBLIC_URL": "https://hermes.acp.test",
    "HERMES_DASHBOARD_OIDC_ISSUER": "https://idp.acp.test:8443",
    "HERMES_DASHBOARD_OIDC_CLIENT_ID": "acp-tableau",
}
# Réclamation de la garde (hermes/image/acp_demarrage.py, verifier_environnement) pour une variable que l'image doit
# fixer. Le nom et la valeur sont revalidés avant d'être passés à docker.
RECLAMATION = re.compile(r"la variable (?P<nom>[A-Z][A-Z0-9_]{0,63}) manque ; l'image la fixe à « (?P<valeur>[^»]*) »")
FORME_VALEUR_RECLAMEE = re.compile(r"[A-Za-z0-9/._:-]{1,256}", re.ASCII)
FORME_PREFIXE = re.compile(r"acp-contrat-[a-z0-9-]{1,40}", re.ASCII)
# Lignes du journal du conteneur reprises par la sonde (le journal complet va dans --journal-conteneur).
MOTIFS_JOURNAL = re.compile(r"REFUS|\[config-migrate\]|skipped|WARNING hermes_cli\.plugins|Traceback|fatal|"
                            r"ERROR|requires hermes")


@dataclass(frozen=True)
class Controle:
    """Un contrôle du job « temoin » : identifiant de l'étape, libellé, rapport JUnit éventuel, lignes du journal
    reprises dans le détail. ``compte`` : faux pour un diagnostic hors verdict."""

    id: str
    libelle: str
    junit: Optional[str] = None
    motifs: Tuple[str, ...] = ()
    compte: bool = True
    detail_max: int = 900


CONTROLES: Tuple[Controle, ...] = (
    Controle("ecrire", "Écriture de l'épinglage témoin (`monter_hermes.py ecrire`)",
             motifs=(r"^Épingles fortes réécrites", r"^OpenRPC :", r"^ATTENTION", r"^Skills ", r"^Refus"),
             detail_max=2500),
    Controle("perimetre", "Fichiers réécrits : seulement les épingles fortes (sinon défaut de l'outil)",
             motifs=(r"^Fichiers modifiés", r"^Hors des épingles fortes", r"^Seulement", r"^Aucun fichier")),
    Controle("verifier", "Concordance de l'épinglage écrit avec la release (`monter_hermes.py verifier`)",
             motifs=(r"^\d+ écart", r"^- ", r"^Aucun écart", r"^Refus")),
    Controle("catalogue", "Catalogue hors ligne (`verifier_catalogue.py`)", motifs=(r"Catalogue", r"^- ", r"rreur")),
    Controle("depot", "Suite du dépôt hors ligne (pytest ; concordance des épingles comprise)", junit="depot.xml"),
    Controle("interface", "Interface : types et Vitest (fixtures réécrites)",
             motifs=(r"Test Files", r"Tests  ", r"FAIL", r"error TS")),
    Controle("image_acp", "Construction de l'image ACP (`FROM` de la release témoin)", motifs=(r"ERROR", r"error:")),
    Controle("image_tests", "Construction de l'image de test", motifs=(r"ERROR", r"error:")),
    Controle("image_factice", "Construction de la cible factice de l'exécutant", motifs=(r"ERROR", r"error:")),
    Controle("image_identite", "Construction de l'image du fournisseur d'identité", motifs=(r"ERROR", r"error:")),
    Controle("version", "`hermes --version` = `HERMES_VERSION` écrite", motifs=(r"^Hermes Agent v", r"^Code :")),
    Controle("compat", "`hermes plugins compat` : greffon acp-poste (noyau compris) accepté",
             motifs=(r"✓", r"DISABLED", r"rror", r"^Code")),
    Controle("compat_temoin", "`hermes plugins compat` : greffon témoin refusé (code 1 attendu)",
             motifs=(r"^Code du témoin",)),
    Controle("sonde", "Démarrage de l'image ACP sur un volume neuf (sonde)",
             motifs=(r"^Démarre :", r"^/api/status :", r"REFUS", r"config-migrate", r"skipped", r"^Refus")),
    Controle("sonde_diag", "Diagnostic HORS VERDICT : même sonde, variables réclamées par la garde ajoutées",
             motifs=(r"^Variables ajoutées", r"^Diagnostic sans objet", r"^Démarre :", r"^/api/status :", r"REFUS",
                     r"config-migrate", r"skipped", r"^Refus"), compte=False, detail_max=2500),
    Controle("pytest_image", "pytest dans l'image de test", junit="pytest-image.xml"),
    Controle("contrat", "Tests de contrat (hors restauration et montée)", junit="contrat.xml"),
)
# Étapes à identifiant qui ne sont pas des contrôles (préalable affiché en tête du tableau).
ETAPES_PREALABLES = ("etiquette",)

RESULTATS = {"success": "réussi", "failure": "**ÉCHEC**", "skipped": "non lancé", "cancelled": "annulé"}
LIMITE_LIGNES_SUITE = 400


# =========================================================================== périmètre de l'écriture


def fichiers_modifies(racine: Path, executer: Executeur) -> List[str]:
    """Chemins modifiés, ajoutés ou supprimés dans la copie de travail (fichiers non suivis compris)."""
    etat = executer(["git", "-C", str(racine), "status", "--porcelain=v1", "-z", "--untracked-files=all"], 60)
    if etat.code != 0:
        raise Refus(f"git status a échoué (code {etat.code}) : {etat.erreur.decode('utf-8', 'replace')[:200]}")
    entrees = etat.sortie.decode("utf-8", "replace").split("\0")
    chemins: List[str] = []
    i = 0
    while i < len(entrees):
        entree = entrees[i]
        i += 1
        if len(entree) < 4:
            continue
        code, chemin = entree[:2], entree[3:]
        chemins.append(chemin)
        if "R" in code or "C" in code:  # renommage ou copie : l'ancien chemin suit, il est aussi touché
            if i < len(entrees) and entrees[i]:
                chemins.append(entrees[i])
            i += 1
    return sorted(set(chemins))


def perimetre(racine: Path, executer: Executeur, sortie: Callable[[str], None] = print) -> int:
    fichiers = fichiers_modifies(racine, executer)
    if not fichiers:
        sortie("Aucun fichier modifié par l'écriture (étiquette témoin égale à l'épinglée : aucune valeur ne change).")
        return 0
    sortie(f"Fichiers modifiés par l'écriture ({len(fichiers)}) : {', '.join(fichiers)}.")
    hors = [f for f in fichiers if f not in mh.EPINGLES_FORTES]
    if hors:
        sortie(f"Hors des épingles fortes (défaut de l'outil) : {', '.join(hors)}.")
        return 1
    sortie(f"Seulement des épingles fortes : {len(fichiers)} fichier(s) sur les {len(mh.EPINGLES_FORTES)} que "
           "l'outil peut écrire.")
    return 0


# =========================================================================== sonde de démarrage


def variables_reclamees(journal: str) -> Dict[str, str]:
    """Variables que la garde de démarrage a réclamées (« la variable X manque ; l'image la fixe à « V » »), nom et
    valeur revalidés ; toute autre forme est ignorée (jamais passée à docker)."""
    trouvees: Dict[str, str] = {}
    for m in RECLAMATION.finditer(journal):
        if FORME_VALEUR_RECLAMEE.fullmatch(m.group("valeur")):
            trouvees[m.group("nom")] = m.group("valeur")
    return trouvees


def _docker(executer: Executeur, *arguments: str, delai: int = 300) -> Resultat:
    resultat = executer(["docker", *arguments], delai)
    if resultat.code != 0:
        raise Refus(f"docker {' '.join(arguments[:3])} … a échoué (code {resultat.code}) : "
                    f"{resultat.erreur.decode('utf-8', 'replace')[-400:]}")
    return resultat


def _statut(executer: Executeur, nom: str) -> Optional[dict]:
    r = executer(["docker", "exec", nom, "curl", "-s", "http://127.0.0.1:9119/api/status"], 60)
    try:
        valeur = json.loads(r.texte) if r.code == 0 else None
    except ValueError:
        return None
    return valeur if isinstance(valeur, dict) else None


def _passerelle_branchee(statut: Optional[dict]) -> bool:
    if not statut:
        return False
    serveur = (statut.get("gateway_platforms") or {}).get("api_server") or {}
    return bool(statut.get("gateway_running")) and serveur.get("state") == "connected"


def resume_statut(statut: Optional[dict]) -> str:
    if not statut:
        return "illisible"
    serveur = (statut.get("gateway_platforms") or {}).get("api_server") or {}
    champs = [f"{cle}={statut.get(cle)!r}" for cle in ("version", "release_date", "config_version",
                                                       "latest_config_version", "gateway_running", "gateway_state")]
    return ", ".join(champs + [f"api_server={serveur.get('state')!r}"])


def sonder(image: str, prefixe: str, executer: Executeur, *, variables: Optional[Mapping[str, str]] = None,
           delai_pret: float = 240, delai_passerelle: float = 180, attendre: Callable[[float], None] = time.sleep,
           horloge: Callable[[], float] = time.monotonic, sortie: Callable[[str], None] = print) -> Tuple[int, str]:
    """Démarre ``image`` sur un volume neuf ; rend (code, journal complet du conteneur). Code 0 : tableau de bord
    prêt ET passerelle branchée ; 1 sinon. Conteneur et volume sont supprimés à la fin, même en échec."""
    if not FORME_PREFIXE.fullmatch(prefixe):
        raise Refus(f"Préfixe « {prefixe} » refusé : acp-contrat-<minuscules, chiffres, tirets> attendu (nettoyage "
                    "de fin de job).")
    nom, volume = f"{prefixe}-hermes", f"{prefixe}-vol"
    env = dict(ENV_SONDE)
    env.update(variables or {})
    journal = ""
    code = 1
    try:
        _docker(executer, "volume", "create", volume)
        # Comme les tests de contrat (Ressources.volume) : volume neuf rendu à l'uid hermes.
        _docker(executer, "run", "--rm", "-v", f"{volume}:/opt/data", "--entrypoint", "sh", image, "-c",
                "chown -hR 10000:10000 /opt/data")
        options: List[str] = []
        for cle, valeur in env.items():
            options += ["-e", f"{cle}={valeur}"]
        _docker(executer, "run", "-d", "--name", nom, "-v", f"{volume}:/opt/data", "--add-host",
                "mcp.context7.com:127.0.0.1", *options, image)
        debut = horloge()
        pret: Optional[float] = None
        arret: Optional[str] = None
        while horloge() - debut < delai_pret:
            etat = executer(["docker", "inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", nom], 60)
            en_marche, _, code_sortie = etat.texte.strip().partition(" ")
            if en_marche != "true":
                arret = f"conteneur arrêté après {int(horloge() - debut)} s, code {code_sortie or 'inconnu'}"
                break
            essai = executer(["docker", "exec", nom, "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                              "http://127.0.0.1:9119/api/status"], 60)
            if essai.texte.strip() == "200":
                pret = horloge() - debut
                break
            attendre(2)
        statut: Optional[dict] = None
        if pret is None:
            raison = arret or f"tableau de bord injoignable après {int(delai_pret)} s"
            sortie(f"Démarre : non ({raison}).")
        else:
            debut_passerelle = horloge()
            statut = _statut(executer, nom)
            while not _passerelle_branchee(statut) and horloge() - debut_passerelle < delai_passerelle:
                attendre(2)
                statut = _statut(executer, nom)
            if _passerelle_branchee(statut):
                code = 0
                sortie(f"Démarre : oui (/api/status 200 en {int(pret)} s ; passerelle et api_server branchés).")
            else:
                sortie(f"Démarre : non (tableau de bord prêt en {int(pret)} s, mais passerelle ou api_server non "
                       f"branchés après {int(delai_passerelle)} s).")
            sortie(f"/api/status : {resume_statut(statut)}")
            etat_acp = executer(["docker", "exec", nom, "cat", "/run/acp/etat-demarrage.json"], 60)
            sortie("État du démarrage d'ACP (/run/acp/etat-demarrage.json) : "
                   + (etat_acp.texte.strip()[:3000] if etat_acp.code == 0 else "illisible"))
            greffon = executer(["docker", "exec", nom, "sh", "-c",
                                "grep -rh 'acp-poste' /opt/data/logs 2>/dev/null | tail -n 12"], 60)
            sortie("Journaux du volume mentionnant acp-poste :")
            for ligne in greffon.texte.splitlines() or ["(aucune ligne)"]:
                sortie(f"  {ligne}")
        journaux = executer(["docker", "logs", nom], 120)
        journal = journaux.texte + journaux.erreur.decode("utf-8", "replace")
        extraits = [ligne for ligne in journal.splitlines() if MOTIFS_JOURNAL.search(ligne)]
        sortie(f"Lignes notables du journal du conteneur ({len(extraits)}, 40 au plus) :")
        for ligne in extraits[:40] or ["(aucune)"]:
            sortie(f"  {ligne}")
    finally:
        executer(["docker", "rm", "-f", "-v", nom], 120)
        executer(["docker", "volume", "rm", "-f", volume], 120)
    return code, journal


# =========================================================================== rapports JUnit


@dataclass
class Suite:
    reussis: int = 0
    ignores: int = 0
    echecs: List[Tuple[str, str]] = field(default_factory=list)
    erreurs: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.reussis + self.ignores + len(self.echecs) + len(self.erreurs)


def _raison(element: ET.Element) -> str:
    message = (element.get("message") or "").strip()
    if not message:
        message = next((l.strip() for l in (element.text or "").splitlines() if l.strip()), "")
    return message.splitlines()[0] if message else "(raison absente du rapport)"


def lire_junit(chemin: Path) -> Suite:
    """Rapport ``--junitxml`` écrit par NOTRE pytest dans le même job (jamais un fichier venu d'ailleurs) ; l'analyseur
    de la bibliothèque standard ne résout aucune entité externe."""
    try:
        racine = ET.parse(chemin).getroot()
    except (OSError, ET.ParseError) as exc:
        raise Refus(f"rapport JUnit {chemin.name} illisible ({type(exc).__name__}).")
    suite = Suite()
    for cas in racine.iter("testcase"):
        ident = f"{cas.get('classname') or ''}::{cas.get('name') or ''}"
        enfants = {enfant.tag: enfant for enfant in cas}
        if "failure" in enfants:
            suite.echecs.append((ident, _raison(enfants["failure"])))
        elif "error" in enfants:
            suite.erreurs.append((ident, _raison(enfants["error"])))
        elif "skipped" in enfants:
            suite.ignores += 1
        else:
            suite.reussis += 1
    return suite


# =========================================================================== tableau des écarts


def _cellule(texte: str, limite: int) -> str:
    texte = " ".join(texte.split())
    if len(texte) > limite:
        texte = texte[: limite - 1] + "…"
    return texte.replace("\\", "\\\\").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def _lire_journal(dossier: Path, identifiant: str) -> Optional[str]:
    chemin = dossier / "journaux" / f"{identifiant}.txt"
    try:
        return chemin.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _detail_journal(controle: Controle, journal: Optional[str]) -> str:
    if journal is None:
        return "journal absent"
    lignes = [l.strip() for l in ANSI.sub("", journal).splitlines() if l.strip()]
    retenues = [l for l in lignes if any(re.search(m, l) for m in controle.motifs)] if controle.motifs else []
    if not retenues:
        retenues = lignes[-2:]
    vues: List[str] = []
    for ligne in retenues:
        if ligne not in vues:
            vues.append(ligne)
    return " ⏎ ".join(vues[:12]) or "journal vide"


def _etiquette_affichee(etiquette: str) -> str:
    return etiquette if FORME_ETIQUETTE_TEMOIN.fullmatch(etiquette) else "(étiquette refusée : hors forme vAAAA.M.J)"


def tableau(etapes: Mapping[str, object], dossier: Path, etiquette: str, epinglee: str) -> Tuple[str, int]:
    """Rend (Markdown, code) : code 0 si chaque contrôle compté a réussi et chaque suite pytest a un rapport non
    vide, 1 sinon."""
    sortie: List[str] = [f"## Témoin de montée de Hermes : {_etiquette_affichee(etiquette)} "
                         f"(épinglée : {_etiquette_affichee(epinglee)})", ""]
    lignes: List[str] = []
    problemes: List[str] = []
    suites: List[Tuple[Controle, Optional[Suite], Optional[str]]] = []
    for prealable in ETAPES_PREALABLES:
        info = etapes.get(prealable)
        issue = info.get("outcome") if isinstance(info, dict) else None
        if issue != "success":
            problemes.append(f"préalable « {prealable} » : {RESULTATS.get(str(issue), 'absent du job')}")
    connus = {c.id for c in CONTROLES} | set(ETAPES_PREALABLES)
    inconnus = [Controle(nom, f"Étape « {nom} » (hors de la liste des contrôles)") for nom in sorted(etapes)
                if nom not in connus]
    for numero, controle in enumerate((*CONTROLES, *inconnus), 1):
        info = etapes.get(controle.id)
        issue = info.get("outcome") if isinstance(info, dict) else None
        resultat = RESULTATS.get(str(issue), "absent du job")
        if controle.junit:
            chemin = dossier / "junit" / controle.junit
            suite: Optional[Suite] = None
            anomalie: Optional[str] = None
            if issue in ("success", "failure"):
                if chemin.is_file():
                    try:
                        suite = lire_junit(chemin)
                    except Refus as refus:
                        anomalie = str(refus)
                else:
                    anomalie = f"rapport JUnit {controle.junit} absent"
            if suite is not None and suite.total == 0:
                anomalie = "aucun test exécuté (rapport vide)"
            if suite is not None:
                detail = (f"{suite.reussis} réussis, {len(suite.echecs)} en échec, {len(suite.erreurs)} en erreur, "
                          f"{suite.ignores} ignorés")
            else:
                detail = "non lancé" if issue not in ("success", "failure") else ""
            if anomalie:
                detail = f"{detail} ; ANOMALIE : {anomalie}" if detail else f"ANOMALIE : {anomalie}"
                if controle.compte:
                    problemes.append(f"{controle.libelle} : {anomalie}")
            if issue == "success" and suite is not None and (suite.echecs or suite.erreurs):
                problemes.append(f"{controle.libelle} : étape réussie malgré des tests en échec (incohérent)")
            suites.append((controle, suite, anomalie))
        else:
            detail = _detail_journal(controle, _lire_journal(dossier, controle.id)) if issue in (
                "success", "failure") else "non lancé (une étape dont il dépend a échoué ou ne s'applique pas)"
        if not controle.compte:
            resultat = f"hors verdict ({resultat})"
        elif issue != "success":
            problemes.append(f"{controle.libelle} : {resultat.strip('*').lower()}")
        lignes.append(f"| {numero} | {_cellule(controle.libelle, 200)} | {resultat} | "
                      f"{_cellule(detail, controle.detail_max)} |")
    comptes = [c for c in (*CONTROLES, *inconnus) if c.compte]
    if problemes:
        sortie.append(f"**Verdict : {len(problemes)} écart(s) ou anomalie(s)** sur {len(comptes)} contrôles comptés "
                      "(le job échoue ; chaque écart est expliqué dans le tableau et dans l'artefact).")
    else:
        sortie.append(f"**Verdict : aucun écart** : les {len(comptes)} contrôles comptés ont réussi.")
    sortie += ["", "| N° | Contrôle | Résultat | Détail |", "|---|---|---|---|", *lignes, ""]
    for controle, suite, anomalie in suites:
        if suite is None:
            continue
        sortie.append(f"### {controle.libelle} : {suite.reussis} réussis, {len(suite.echecs)} en échec, "
                      f"{len(suite.erreurs)} en erreur, {suite.ignores} ignorés")
        sortie.append("")
        en_cause = [("échec", t, r) for t, r in suite.echecs] + [("erreur", t, r) for t, r in suite.erreurs]
        if not en_cause:
            sortie += ["Aucun test en échec ni en erreur.", ""]
            continue
        frequentes = Counter(_cellule(r, 300) for _, _, r in en_cause).most_common(10)
        sortie += ["Raisons les plus fréquentes :", "", "| Tests | Raison (première ligne) |", "|---|---|"]
        sortie += [f"| {n} | {r} |" for r, n in frequentes]
        sortie += ["", "| Nature | Test | Raison (première ligne) |", "|---|---|---|"]
        for nature, test, raison in en_cause[:LIMITE_LIGNES_SUITE]:
            sortie.append(f"| {nature} | {_cellule(test, 200)} | {_cellule(raison, 300)} |")
        if len(en_cause) > LIMITE_LIGNES_SUITE:
            sortie.append(f"| … | {len(en_cause) - LIMITE_LIGNES_SUITE} de plus | voir le rapport JUnit de l'artefact |")
        sortie.append("")
    if problemes:
        sortie += ["### Écarts et anomalies du verdict", ""] + [f"- {_cellule(p, 600)}" for p in problemes] + [""]
    sortie.append("Journaux complets, rapports JUnit et correctif d'épinglage : artefact du job (dossier "
                  "`/tmp/temoin`). Rien n'est committé ni poussé ; la borne `requires_hermes` n'est jamais modifiée.")
    return "\n".join(sortie) + "\n", (1 if problemes else 0)


def etiquette_epinglee(racine: Path, executer: Executeur) -> str:
    """Étiquette épinglée par le commit (HEAD), avant toute écriture de la copie de travail."""
    r = executer(["git", "-C", str(racine), "show", f"HEAD:{mh.EPINGLE}"], 60)
    if r.code != 0:
        raise Refus(f"git show HEAD:{mh.EPINGLE} a échoué (code {r.code}).")
    m = re.search(r"^HERMES_TAG=(\S+)$", r.texte, re.M)
    if not m:
        raise Refus(f"HERMES_TAG introuvable dans HEAD:{mh.EPINGLE}.")
    return m.group(1)


# =========================================================================== entrée


def main(argv: Optional[Sequence[str]] = None, racine: Path = RACINE,
         executer: Executeur = mh.executer_reel) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    description = (__doc__ or "Témoin de montée de version de Hermes.").split("\n\n")[0]
    analyseur = argparse.ArgumentParser(prog="temoin_hermes.py", description=description)
    sous = analyseur.add_subparsers(dest="commande", required=True)
    sous.add_parser("perimetre", help="fichiers réécrits : seulement les épingles fortes")
    p_sonde = sous.add_parser("sonde", help="démarrage de l'image d'ACP sur un volume neuf")
    p_sonde.add_argument("--image", required=True)
    p_sonde.add_argument("--prefixe", required=True)
    p_sonde.add_argument("--variables-de", dest="variables_de", type=Path,
                         help="journal d'une sonde précédente : ajoute les variables que la garde a réclamées")
    p_sonde.add_argument("--journal-conteneur", dest="journal_conteneur", type=Path)
    p_tableau = sous.add_parser("tableau", help="tableau des écarts (Markdown)")
    p_tableau.add_argument("--etapes-env", dest="etapes_env", required=True,
                           help="variable d'environnement qui porte toJSON(steps)")
    p_tableau.add_argument("--dossier", required=True, type=Path)
    p_tableau.add_argument("--etiquette", required=True)
    p_tableau.add_argument("--sortie", type=Path)
    arguments = analyseur.parse_args(argv)
    try:
        if arguments.commande == "perimetre":
            return perimetre(racine, executer)
        if arguments.commande == "sonde":
            variables: Dict[str, str] = {}
            if arguments.variables_de is not None:
                try:
                    texte = arguments.variables_de.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    raise Refus(f"journal {arguments.variables_de} illisible.")
                variables = variables_reclamees(texte)
                if not variables:
                    print("Diagnostic sans objet : la garde n'a réclamé aucune variable d'image dans ce journal.")
                    return 0
                print("Variables ajoutées (diagnostic, hors verdict) : "
                      + ", ".join(f"{k}={v}" for k, v in sorted(variables.items())))
            code, journal = sonder(arguments.image, arguments.prefixe, executer, variables=variables)
            if arguments.journal_conteneur is not None:
                arguments.journal_conteneur.parent.mkdir(parents=True, exist_ok=True)
                arguments.journal_conteneur.write_text(journal, encoding="utf-8")
            return code
        brut = os.environ.get(arguments.etapes_env)
        if brut is None:
            raise Refus(f"variable d'environnement {arguments.etapes_env} absente.")
        try:
            etapes = json.loads(brut)
        except ValueError:
            raise Refus(f"{arguments.etapes_env} n'est pas du JSON.")
        if not isinstance(etapes, dict):
            raise Refus(f"{arguments.etapes_env} n'est pas un objet JSON.")
        texte, code = tableau(etapes, arguments.dossier, arguments.etiquette, etiquette_epinglee(racine, executer))
        if arguments.sortie is not None:
            arguments.sortie.parent.mkdir(parents=True, exist_ok=True)
            arguments.sortie.write_text(texte, encoding="utf-8")
        print(texte)
        return code
    except Refus as refus:
        print(f"Refus : {refus}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
