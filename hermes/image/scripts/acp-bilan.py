"""Bilan quotidien d'ACP (étape P7, cahier P7 § 7, décision P7-6 ; correction K1).

Lancé par une tâche cron NATIVE de Hermes en mode ``no_agent`` (aucun modèle, aucun jeton : cron/scheduler.py), que
SEUL le propriétaire crée (bouton « Créer le bilan quotidien » de l'Accueil, ou page Cron) ; l'agent ne peut pas créer
de tâche cron (``cronjob`` coupé par la managed scope). Hermes lance ce fichier par son interpréteur, en
sous-processus de la passerelle (ou du tableau de bord pour « Exécuter maintenant »), à l'environnement assaini.

Ce script N'ACCEPTE AUCUNE ENTRÉE : il ignore ses arguments, son entrée standard et l'environnement, sauf
``HERMES_HOME`` (exigé, absolu) ; les autres variables ``HERMES_*`` et ``ACP_*`` sont retirées avant tout import de
Hermes, pour qu'aucune ne redirige une base. Il charge le noyau du greffon acp-poste comme le tableau de bord
(``meta.module_noyau``), lit la base, et enfile UNE notification ``bilan:<AAAA-MM-JJ>`` (jour de Paris), compteurs
seulement (``noyau/bilan.py``). Une tâche ne peut rien lui faire faire d'autre.

Sortie standard : une ligne, « bilan enfilé » ou « bilan déjà enfilé aujourd'hui » (livrée en ``local``). Erreur :
une ligne sur la sortie d'erreur et le code 1, jamais un faux succès.

Garde de démarrage (``acp_demarrage.py``) : ce fichier est déposé par root dans ``<HERMES_HOME>/scripts/`` à chaque
démarrage (copie, jamais un lien : Hermes refuse un script qui résout hors de ``scripts/``) ; ce dossier n'admet que
ce fichier, à root, mode 0644, d'empreinte SHA-256 connue de l'image (``EMPREINTES_BILAN_ADMISES``).
"""

import importlib.util
import os
import sys
from pathlib import Path

GREFFON = Path("/opt/hermes/plugins/acp-poste")


class RefusBilan(Exception):
    """Refus de ce script, au message français écrit ici (aucune valeur reçue n'y figure)."""


def _environnement_ferme() -> Path:
    """Garde ``HERMES_HOME`` (exigé, absolu, répertoire existant) et retire toute autre variable de Hermes ou d'ACP."""
    home = os.environ.get("HERMES_HOME", "")
    if not home or not os.path.isabs(home) or not os.path.isdir(home):
        raise RefusBilan("HERMES_HOME absent ou invalide : bilan non enfilé.")
    for nom in list(os.environ):
        if nom != "HERMES_HOME" and nom.startswith(("HERMES_", "ACP_")):
            del os.environ[nom]
    return Path(home)


def _noyau():
    spec = importlib.util.spec_from_file_location("acp_poste_greffon_meta", GREFFON / "meta.py")
    if spec is None or spec.loader is None:
        raise RefusBilan("greffon acp-poste introuvable dans l'image : bilan non enfilé.")
    meta = importlib.util.module_from_spec(spec)
    sys.modules["acp_poste_greffon_meta"] = meta
    spec.loader.exec_module(meta)
    return meta.sous_module_noyau("base"), meta.sous_module_noyau("bilan")


def main() -> int:
    try:
        _environnement_ferme()
        base, bilan = _noyau()
        with base.connexion() as conn:
            resultat = bilan.enfiler(conn)
    except RefusBilan as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    except Exception as exc:  # noqa: BLE001 — le type seul : un message pourrait porter un chemin ou une valeur
        print(f"bilan non enfilé ({type(exc).__name__})", file=sys.stderr, flush=True)
        return 1
    print("bilan enfilé" if resultat["nouveau"] else "bilan déjà enfilé aujourd'hui", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
