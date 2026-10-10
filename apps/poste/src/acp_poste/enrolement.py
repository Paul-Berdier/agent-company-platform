"""Commande ``acp-poste enroler`` (cahier P5 § 5.1, décisions D48 et D49).

1. Le propriétaire crée un code d'enrôlement à usage unique (10 min) sur la page Poste.
2. Dans le compte du poste, ``acp-poste enroler`` lit ce code par **saisie masquée** (``--code-stdin`` : sur l'entrée
   standard, pour le lanceur de test et le repli dans le compte du propriétaire) ; le code n'est ni affiché ni
   journalisé.
3. Hermes rend, une seule fois, le jeton machine (256 bits) : il va **directement** au coffre DPAPI, jamais à
   l'écran ; seule l'empreinte ``XXXX-XXXX`` est affichée, à recopier sur la page Poste avant de « Confirmer ».

Refus : poste déjà enrôlé sans ``--remplacer`` (code 2) ; code au format invalide (2) ; code refusé par Hermes
(inconnu, expiré ou déjà utilisé, 2) ; Hermes injoignable (1).
"""

from __future__ import annotations

import getpass
import json
import sys
from datetime import UTC, datetime
from typing import Callable

from .chemins import commande_poste
from .coffre import CoffreErreur, ecrire_atomiquement
from .contexte import Contexte
from .jeton import CodeEnrolement, Jeton, JetonInvalide
from .journal import Journal
from .politique import Politique
from .protocole import HermesIndisponible, HorsContrat, Protocole, Refus

DEJA_ENROLE = ("Poste déjà enrôlé (empreinte {empreinte}) : révoquez l'ancien poste sur la page Poste, puis lancez "
               f"« {commande_poste('enroler --remplacer')} ».")
CODE_INVALIDE = ("Code d'enrôlement au format invalide : copiez-le tel quel depuis la page Poste (acpe_ suivi de 43 "
                 "caractères).")


def identite(contexte: Contexte) -> dict | None:
    try:
        donnees = json.loads(contexte.emplacements.machine.read_text(encoding="utf-8"))
        return donnees if isinstance(donnees, dict) else None
    except (OSError, ValueError):
        return None


def enroler(contexte: Contexte, politique: Politique, journal: Journal, *, code_stdin: bool, remplacer: bool,
            lire_code: Callable[[str], str] | None = None) -> int:
    try:
        deja = contexte.coffre.present("jeton-machine")
    except CoffreErreur as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if deja and not remplacer:
        empreinte = (identite(contexte) or {}).get("empreinte", "inconnue")
        print(DEJA_ENROLE.format(empreinte=empreinte), file=sys.stderr)
        return 2
    brut = sys.stdin.readline() if code_stdin else (lire_code or getpass.getpass)(
        "Code d'enrôlement (collé, saisie masquée) : ")
    try:
        code = CodeEnrolement((brut or "").strip())
    except JetonInvalide:
        print(CODE_INVALIDE, file=sys.stderr)
        return 2
    journal.masquer_valeur("code-enrolement", code.valeur_secrete())
    try:
        protocole = Protocole(contexte.client(politique))
        try:
            reponse = protocole.enroler(code, nom=politique.poste.nom)
        except HermesIndisponible as exc:
            journal.ecrire("erreur", "enrolement_impossible", exc.message)
            print(exc.message, file=sys.stderr)
            return 1
        except (HorsContrat, Refus) as exc:
            journal.ecrire("erreur", "enrolement_refuse", exc.message, statut=exc.statut, code=exc.code)
            print(exc.message, file=sys.stderr)
            return 2
        jeton = Jeton(reponse.jeton)
        journal.masquer_valeur("jeton-machine", jeton.valeur_secrete())
        try:
            contexte.coffre.ecrire("jeton-machine", jeton.valeur_secrete())
        except CoffreErreur as exc:
            journal.ecrire("erreur", "coffre", str(exc))
            print(f"{exc} Le jeton reçu est perdu : révoquez ce poste sur la page Poste et recommencez.",
                  file=sys.stderr)
            return 2
        ecrire_atomiquement(contexte.emplacements.machine, json.dumps(
            {"machine_id": reponse.machine_id, "empreinte": jeton.empreinte,
             "enrole_le": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}).encode("utf-8"))
        journal.ecrire("info", "enrolement", "Poste enrôlé : empreinte à confirmer sur la page Poste.",
                       machine=reponse.machine_id, empreinte=jeton.empreinte)
        print(f"Poste enrôlé ({reponse.machine_id}). Empreinte : {jeton.empreinte}")
        print("Recopiez cette empreinte sur la page Poste puis cliquez « Confirmer » : le poste ne compte qu'après "
              "cette confirmation.")
        return 0
    finally:
        journal.masquer_valeur("code-enrolement", None)
