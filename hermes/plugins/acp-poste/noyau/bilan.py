"""Bilan quotidien (étape P7, cahier P7 § 7, décision P7-6).

Enfilé par le script ``acp-bilan.py`` (image : ``/opt/acp/scripts/acp-bilan.py``, déposé à chaque démarrage dans
``<HERMES_HOME>/scripts/``) qu'une tâche cron NATIVE ``no_agent`` lance sans modèle ni jeton, une fois par jour ; la
tâche n'est créée que par le PROPRIÉTAIRE (bouton de l'Accueil ou page Cron), jamais par l'agent (``cronjob`` coupé).

UNE notification ``bilan:<AAAA-MM-JJ>`` par jour de Paris (clé unique : deux exécutions le même jour n'en font
qu'une), envoyée même quand rien n'a bougé (le silence se confondrait avec une panne). COMPTEURS SEULEMENT : aucun
titre de carte, aucune question, aucune consigne ; 300 caractères au plus (D32). Ce qui ne se lit pas est dit
« inconnu », jamais compté zéro. Le lien (relatif, ``/``) est préfixé par l'URL publique à l'envoi, dans la passerelle
(correction K3) : le sous-processus du cron, à l'environnement assaini, n'a pas à la connaître.

Limite dite (correction K22) : l'envoi part du fil de la passerelle ; après un redémarrage pendant une pause
générale, le bilan reste en file jusqu'à la reprise.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import base, notifications, presence, projets, questions
from . import textes as T

GENRE = "bilan"
FUSEAU = "Europe/Paris"
ETATS_EN_COURS = ("creation", "actif")


def jour_de_paris(epoch: Optional[float] = None) -> datetime:
    """Instant en heure de Paris. Sans base des fuseaux, l'erreur remonte : jamais une date devinée (un jour faux
    ferait partir deux bilans, ou aucun)."""
    from zoneinfo import ZoneInfo

    instant = datetime.fromtimestamp(base.maintenant() if epoch is None else epoch, tz=timezone.utc)
    return instant.astimezone(ZoneInfo(FUSEAU))


def _pluriel(n: int, singulier: str, pluriel: str) -> str:
    return f"{n} {singulier if abs(n) < 2 else pluriel}"


def compter(conn) -> Dict[str, Any]:
    """Compteurs du bilan, chacun lu par une fonction existante du noyau ; un bloc illisible vaut ``None``."""
    resultat: Dict[str, Any] = {"projets": None, "a_traiter": None, "executant": None}
    try:
        liste = projets.lister(conn)
        en_cours = [p for p in liste if p["etat"] in ETATS_EN_COURS]
        faites = [p["compteurs"].get("faites") for p in en_cours]
        totaux = [p["compteurs"].get("total") for p in en_cours]
        connus = all(isinstance(v, int) for v in faites + totaux)
        resultat["projets"] = {"en_cours": len(en_cours), "en_pause": sum(1 for p in liste if p["etat"] == "en_pause"),
                               "faites": sum(faites) if connus else None, "total": sum(totaux) if connus else None}
    except Exception:  # noqa: BLE001 — base ou tableau illisible : « inconnu », jamais zéro
        pass
    try:
        compteurs = questions.file_questions(conn)["compteurs"]
        resultat["a_traiter"] = {cle: int(compteurs[cle]) for cle in ("questions", "decisions", "revues", "arretees")}
    except Exception:  # noqa: BLE001
        pass
    try:
        poste = presence.etat_poste(conn)
        resultat["executant"] = {"etat": poste.get("etat"), "hors_ligne_depuis": poste.get("hors_ligne_depuis")}
    except Exception:  # noqa: BLE001
        pass
    return resultat


def _projets(bloc: Optional[Dict[str, Any]]) -> str:
    if bloc is None:
        return T.BILAN_PROJETS_INCONNUS
    n = int(bloc["en_cours"])
    texte = T.BILAN_AUCUN_PROJET if n == 0 else _pluriel(n, "projet en cours", "projets en cours")
    if n and bloc["faites"] is not None and bloc["total"]:
        texte += f" ({T.cartes(int(bloc['faites']), 'faite')} sur {int(bloc['total'])})"
    if bloc["en_pause"]:
        texte += f", {bloc['en_pause']} en pause"
    return texte


def _a_traiter(bloc: Optional[Dict[str, int]]) -> str:
    if bloc is None:
        return T.BILAN_DEMANDES_INCONNUES
    morceaux: List[str] = []
    for cle, singulier, pluriel in (("questions", "question", "questions"), ("decisions", "décision", "décisions"),
                                    ("revues", "revue", "revues"),
                                    ("arretees", "carte arrêtée", "cartes arrêtées")):
        if bloc[cle]:
            morceaux.append(_pluriel(bloc[cle], singulier, pluriel))
    if not morceaux:
        return T.BILAN_RIEN_POUR_VOUS
    liste = morceaux[0] if len(morceaux) == 1 else ", ".join(morceaux[:-1]) + " et " + morceaux[-1]
    return f"{liste} pour vous"


def _executant(bloc: Optional[Dict[str, Any]]) -> str:
    if bloc is None or not bloc.get("etat"):
        return T.BILAN_EXECUTANT_INCONNU
    etat = bloc["etat"]
    if etat == "hors_ligne" and bloc.get("hors_ligne_depuis"):
        return T.BILAN_EXECUTANT_HORS_LIGNE_DEPUIS.format(
            heure=jour_de_paris(int(bloc["hors_ligne_depuis"])).strftime("%H:%M"))
    return T.BILAN_EXECUTANT.get(etat, T.BILAN_EXECUTANT_INCONNU)


def texte(compte: Dict[str, Any], jour: datetime) -> str:
    """Texte du bilan (300 caractères au plus, masqué) : compteurs seulement."""
    return notifications.texte(T.NOTIF_BILAN, jour=jour.strftime("%d/%m"), projets=_projets(compte.get("projets")),
                               demandes=_a_traiter(compte.get("a_traiter")),
                               executant=_executant(compte.get("executant")))


def enfiler(conn) -> Dict[str, Any]:
    """Enfile le bilan du jour de Paris (UNE ligne par jour). Rend ``{cle, nouveau, texte}`` ; ``nouveau`` vaut faux si
    le bilan du jour était déjà en file (deuxième exécution le même jour). Journal ``bilan``."""
    jour = jour_de_paris()
    cle = f"{GENRE}:{jour.strftime('%Y-%m-%d')}"
    contenu = texte(compter(conn), jour)
    with base.transaction(conn):
        nouveau = notifications.enfiler_dans(conn, cle=cle, genre=GENRE, texte_notif=contenu)
        if nouveau:
            base.journaliser(conn, "acp-poste:bilan", "bilan", cible=cle)
    return {"cle": cle, "nouveau": nouveau, "texte": contenu}
