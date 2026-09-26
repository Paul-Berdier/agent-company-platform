"""Preuve n° 1 du cahier P5 (§ 16) : archive du relevé ``model/list`` du compte, sans identifiant.

``acp-poste preuve model-list`` (console du compte du poste, geste du propriétaire) lance la sonde Codex et écrit
``%LOCALAPPDATA%\\ACP\\preuves\\model-list-<date>.json`` : champs de la liste blanche du § 9.4, version de Codex, date,
origine de la liste. Le fichier est balayé par la garde « aucun identifiant » avant écriture ; le propriétaire le
relit avant de le copier sous ``docs/refonte/preuves/p5/`` avec son SHA-256.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime

from acp_poste_contrat.inventaire import identifiant_trouve

from .coffre import ecrire_atomiquement
from .contexte import Contexte
from .politique import Politique
from .sondes_codex import sonder_codex
from .verrou import Verrou, VerrouOccupe


def preuve_model_list(contexte: Contexte, politique: Politique, valeurs_exactes: list[str]) -> int:
    if politique.codex is None:
        print("Section [codex] absente de poste.toml : preuve impossible.", file=sys.stderr)
        return 2
    try:
        verrou = Verrou(contexte.emplacements.verrou_sondes).prendre()
    except VerrouOccupe:
        print("Une sonde est en cours dans le service : réessayez dans une minute.", file=sys.stderr)
        return 2
    try:
        resultat = asyncio.run(sonder_codex(politique.codex, contexte.emplacements,
                                            delai_s=float(politique.sondes.delai_sonde_s),
                                            prefixe=contexte.lanceurs.get("codex"),
                                            environnement=contexte.environnement))
    finally:
        verrou.rendre()
    releve = resultat.releve
    instant = datetime.now(UTC)
    preuve = {"preuve": "model-list", "releve_le": releve["releve_le"], "version_codex": releve["version_cli"],
              "origine_liste": releve["origine_liste"], "etat": releve["etat"], "detail": releve["detail"],
              "connexion": resultat.connexion, "modeles": releve["modeles"]}
    trouve = identifiant_trouve(preuve, valeurs_exactes=valeurs_exactes)
    if trouve:
        print(f"Preuve retenue par la garde « aucun identifiant » : {trouve.split(' : ')[0]}.", file=sys.stderr)
        return 2
    contenu = json.dumps(preuve, ensure_ascii=False, indent=2).encode("utf-8")
    nom = f"model-list-{instant.strftime('%Y%m%dT%H%M%SZ')}.json"
    ecrire_atomiquement(contexte.emplacements.preuves / nom, contenu)
    print(f"Preuve écrite : preuves\\{nom} (dossier ACP du compte du poste), SHA-256 "
          f"{hashlib.sha256(contenu).hexdigest()} ; {len(releve['modeles'])} modèles, origine « "
          f"{releve['origine_liste']} », état « {releve['etat']} ».")
    return 0 if releve["etat"] == "ok" else 1
