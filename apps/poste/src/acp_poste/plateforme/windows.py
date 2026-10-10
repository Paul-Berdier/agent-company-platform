"""Plateforme Windows : le poste de P5 (cahier P5 § 3 à § 9), inchangé.

- Emplacements : dossiers connus du compte par ``SHGetKnownFolderPath`` (:func:`acp_poste.chemins.emplacements_du_compte`).
- Coffre : DPAPI du compte du poste (:class:`acp_poste.coffre.CoffreDPAPI`).
- Processus : Job Object ``KILL_ON_JOB_CLOSE`` attaché avant la première instruction
  (:func:`acp_poste.local_runner.spawn_fenced_process`) ; un seul compte, ``acp-poste`` : aucun UID par agent.
- Bac à sable : ``windows.sandbox="elevated"`` et ``windowsSandbox/readiness`` (:mod:`acp_poste.sondes_codex`).

Le poste Windows n'exécute aucune carte en P6 (``peut_executer: false``, cahier P6 § 18) : l'exécution sous Windows
reste une étape ultérieure, et ce module ne la prétend pas.
"""

from __future__ import annotations

from typing import Any

from ..chemins import Emplacements, emplacements_du_compte
from ..coffre import CoffreDPAPI


class PlateformeWindows:
    nom = "windows"

    def emplacements(self) -> Emplacements:
        return emplacements_du_compte()

    def coffre(self, emplacements: Emplacements) -> CoffreDPAPI:
        return CoffreDPAPI(emplacements.secrets)

    def infos(self) -> dict[str, Any]:
        from ..inventaire import version_windows

        return {"plateforme": "windows", "hote": "pc", "noyau": None, "windows": version_windows()}
