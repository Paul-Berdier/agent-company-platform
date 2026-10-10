#!/usr/bin/env python3
"""Contrôle du relevé de la sonde R0 AVANT sa publication (cahier P6 § 4.1 et § 15, décision D88 du dépôt).

La sonde R0 tourne dans le projet Railway JETABLE « acp-sonde », lancé par le propriétaire (Start Command
« /usr/local/bin/acp-poste sonde-plateforme --json ») ; sa sortie JSON est copiée depuis les journaux de Railway.
Ce script, lancé sur le PC du propriétaire (ou par un agent sur le fichier qu'il lui remet), ne contacte rien :

1. extrait l'objet JSON du texte collé (les lignes de journal autour sont ignorées ; un objet tronqué est refusé) ;
2. vérifie sa forme : protocole ``acp-sonde-plateforme/1``, horodatage, relevés numérotés, verdict complet ;
3. vérifie la COHÉRENCE du verdict avec les relevés (régime A seulement si les points 4, 5, 6 et 7 le permettent ;
   ``uid_separes`` seulement si les quatre essais du point 7 sont conformes) : un relevé retouché à la main est refusé ;
4. rejoue la garde « aucun identifiant » du contrat (cahier P5 § 11.3) et le balayage des secrets ;
5. affiche le verdict en français et, avec ``--sortie``, écrit le relevé normalisé (JSON trié, LF) à publier tel quel
   dans ``docs/refonte/preuves/`` (le document docs/refonte/executant.md renvoie à ce fichier).

**Bibliothèque standard seulement** (relecture de P6) : lancé par le propriétaire avec le Python de son PC, depuis un
clone neuf, sans environnement virtuel. Les motifs de secrets sont ceux du contrat, chargés depuis leur fichier
(``acp_poste_contrat/motifs_secrets.py``, sans dépendance) ; la garde « aucun identifiant » en est la copie, tenue
en parité avec ``acp_poste_contrat.inventaire.identifiant_trouve`` par ``scripts/tests/test_verifier_releve_r0.py``.

Codes : 0 relevé publiable ; 1 relevé refusé (raison en français) ; 2 utilisation (fichier illisible, motifs du
contrat introuvables).

Usage :
    python scripts/verifier_releve_r0.py <fichier collé | -> [--sortie docs/refonte/preuves/r0-sonde.json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

RACINE = Path(__file__).resolve().parents[1]
MOTIFS_SECRETS = RACINE / "hermes" / "plugins" / "acp-poste" / "contrat" / "acp_poste_contrat" / "motifs_secrets.py"

PROTOCOLE = "acp-sonde-plateforme/1"
POINTS_ATTENDUS = {"4.unshare_root", "4.unshare_10003", "7.id", "7.environ_pid1", "7.fichier_root", "7.kill_pid1",
                   "9.codex_version", "9.claude_version"}
CLES_VERDICT = {"regime", "bwrap", "proc_neuf", "reseau_coupe", "uid_separes", "raison"}
HORODATAGE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class Refus(Exception):
    """Relevé non publiable (message français)."""


class MotifsIntrouvables(Exception):
    """Le fichier des motifs du contrat manque (clone incomplet) : utilisation, code 2."""


def _motif_trouve():
    """``motif_trouve`` du contrat, chargé depuis son FICHIER (sans le paquet, dont ``__init__`` importe pydantic)."""
    try:
        spec = importlib.util.spec_from_file_location("acp_motifs_secrets", MOTIFS_SECRETS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, AttributeError) as exc:
        raise MotifsIntrouvables(f"Motifs de secrets du contrat introuvables ({type(exc).__name__}) : lancez ce "
                                 "script depuis un clone complet du dépôt.") from None
    return module.motif_trouve


# Garde « aucun identifiant » : COPIE de acp_poste_contrat.inventaire (_raison_valeur, identifiant_trouve), en parité
# vérifiée par les tests ; ne lit que des chaînes décodées.
_LECTEUR = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_UNC = re.compile(r"(?:^|\s)\\\\[^\\\s]")
_PROFIL = re.compile(r"[\\/]users[\\/]", re.IGNORECASE)


def raison_identifiant(texte: str, motif_trouve) -> str | None:
    nom = motif_trouve(texte)
    if nom is not None:
        return f"ce qui ressemble à un secret ({nom})"
    if "acpm_" in texte or "acpe_" in texte:
        return "jeton machine ou code d'enrôlement d'ACP"
    if "@" in texte:
        return "adresse électronique (« @ »)"
    if _LECTEUR.search(texte):
        return "chemin de lecteur"
    if _UNC.search(texte):
        return "chemin réseau (UNC)"
    if _PROFIL.search(texte):
        return "chemin de profil utilisateur"
    return None


def identifiant_trouve(objet: Any, motif_trouve) -> str | None:
    """« <chemin> : <raison> » pour la première chaîne (ou clé) refusée, ou ``None`` ; parcours itératif."""
    pile: list = [("valeur", objet, "")]
    while pile:
        genre, courant, chemin = pile.pop()
        if genre == "cle":
            raison = raison_identifiant(courant, motif_trouve)
            if raison:
                return f"{chemin} : clé refusée ({raison})"
            continue
        if isinstance(courant, str):
            raison = raison_identifiant(courant, motif_trouve)
            if raison:
                return f"{chemin or 'valeur'} : {raison}"
        elif isinstance(courant, Mapping):
            enfants = []
            for cle, valeur in courant.items():
                sous = f"{chemin}.{cle}" if chemin else str(cle)
                if isinstance(cle, str):
                    enfants.append(("cle", cle, sous))
                enfants.append(("valeur", valeur, sous))
            pile.extend(reversed(enfants))
        elif isinstance(courant, (list, tuple)):
            pile.extend(("valeur", valeur, f"{chemin}[{i}]") for i, valeur in reversed(list(enumerate(courant))))
    return None


def secret_trouve(objet: Any, motif_trouve) -> str | None:
    """Nom du premier motif de secret dans une chaîne ou une clé, ou ``None`` (comme ``machine.secret_trouve``)."""
    pile: list = [objet]
    while pile:
        courant = pile.pop()
        if isinstance(courant, str):
            nom = motif_trouve(courant)
            if nom:
                return nom
        elif isinstance(courant, Mapping):
            for cle, valeur in courant.items():
                pile.append(valeur)
                if isinstance(cle, str):
                    pile.append(cle)
        elif isinstance(courant, (list, tuple)):
            pile.extend(courant)
    return None


def extraire(texte: str) -> dict[str, Any]:
    """Premier objet JSON complet du texte : de la première ligne qui commence par « { » à l'accolade qui le ferme."""
    debut = next((i for i, l in enumerate(texte.splitlines()) if l.strip().startswith("{")), None)
    if debut is None:
        raise Refus("Aucun objet JSON dans le texte fourni : copiez la sortie entière de la sonde.")
    morceau = "\n".join(texte.splitlines()[debut:])
    try:
        objet, _fin = json.JSONDecoder().raw_decode(morceau.strip())
    except ValueError:
        raise Refus("Relevé JSON incomplet ou illisible (copie tronquée ?) : rien n'est publié.") from None
    if not isinstance(objet, dict):
        raise Refus("Le relevé doit être un objet JSON.")
    return objet


def _code(releves: dict[str, Any], point: str) -> int | None:
    return releves[point]["code"] if point in releves else None


def verifier(releve: dict[str, Any], motif_trouve=None) -> dict[str, Any]:
    motif_trouve = motif_trouve or _motif_trouve()
    if releve.get("protocole") != PROTOCOLE:
        raise Refus(f"Protocole « {releve.get('protocole')} » : « {PROTOCOLE} » attendu (acp-poste sonde-plateforme).")
    if not isinstance(releve.get("sonde_le"), str) or not HORODATAGE.match(releve["sonde_le"]):
        raise Refus("Horodatage « sonde_le » absent ou mal formé.")
    verdict = releve.get("verdict")
    if not isinstance(verdict, dict) or set(verdict) != CLES_VERDICT:
        raise Refus(f"Verdict incomplet : clés attendues {sorted(CLES_VERDICT)}.")
    liste = releve.get("releves")
    if not isinstance(liste, list) or not all(isinstance(r, dict) and {"point", "commande", "code", "sortie"} <= set(r)
                                              for r in liste):
        raise Refus("Relevés absents ou mal formés.")
    releves = {r["point"]: r for r in liste}
    manquants = POINTS_ATTENDUS - set(releves)
    if manquants:
        raise Refus(f"Points de la sonde absents : {', '.join(sorted(manquants))}.")
    if not isinstance(releve.get("plateforme"), dict):
        raise Refus("Bloc « plateforme » absent.")

    uid = (_code(releves, "7.id") == 0 and str(releves["7.id"]["sortie"]).strip().endswith("10003")
           and all(_code(releves, p) not in (0, None) for p in ("7.environ_pid1", "7.fichier_root", "7.kill_pid1")))
    if verdict["uid_separes"] is not uid:
        raise Refus("Verdict « uid_separes » incohérent avec les relevés du point 7 : relevé refusé.")
    essais = [_code(releves, p) for p in ("6a.true", "6b.ecriture_hors", "6c.reseau", "6d.auth")]
    regime_a = (_code(releves, "4.unshare_root") == 0 and _code(releves, "4.unshare_10003") == 0
                and _code(releves, "5.bwrap") == 0 and essais[0] == 0 and all(c not in (0, None) for c in essais[1:])
                and uid)
    if (verdict["regime"] == "A") is not regime_a or verdict["regime"] not in ("A", "B"):
        raise Refus(f"Régime « {verdict['regime']} » incohérent avec les relevés des points 4 à 7 : relevé refusé.")

    raison = identifiant_trouve(releve, motif_trouve)
    if raison:
        raise Refus(f"Identifiant dans le relevé ({raison}) : rien n'est publié.")
    motif = secret_trouve(releve, motif_trouve)
    if motif:
        raise Refus(f"Motif de secret dans le relevé ({motif}) : rien n'est publié.")
    return verdict


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):  # console Windows : accents garantis
        reconfigurer = getattr(flux, "reconfigure", None)
        if reconfigurer is not None:
            try:
                reconfigurer(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass
    analyseur = argparse.ArgumentParser(prog="verifier_releve_r0")
    analyseur.add_argument("fichier", help="texte collé depuis les journaux de Railway, ou « - » (entrée standard)")
    analyseur.add_argument("--sortie", type=Path, help="relevé normalisé à publier (JSON trié, LF)")
    options = analyseur.parse_args(argv)
    try:
        texte = sys.stdin.read() if options.fichier == "-" else Path(options.fichier).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Lecture impossible ({type(exc).__name__}).", file=sys.stderr)
        return 2
    try:
        motif_trouve = _motif_trouve()
    except MotifsIntrouvables as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        releve = extraire(texte)
        verdict = verifier(releve, motif_trouve)
    except Refus as exc:
        print(f"Relevé R0 refusé : {exc}", file=sys.stderr)
        return 1
    print(f"Relevé R0 publiable ({releve['sonde_le']}) : régime {verdict['regime']}, bubblewrap {verdict['bwrap']}, "
          f"UID séparés : {'oui' if verdict['uid_separes'] else 'non'}. {verdict['raison']}")
    if options.sortie:
        options.sortie.parent.mkdir(parents=True, exist_ok=True)
        options.sortie.write_text(json.dumps(releve, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8", newline="\n")
        print(f"Écrit : {options.sortie}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
