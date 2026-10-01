"""Contexte d'exécution d'une commande ``acp-poste`` : emplacements, coffre, compte, injections de test.

En production, :meth:`Contexte.du_compte` prend les dossiers connus de Windows du compte courant et le coffre DPAPI.
Les tests et le bout en bout local (``apps/poste/tests/e2e/lancer_poste.py``) construisent un contexte sur une
racine jetable, avec une autorité de test, une résolution forcée vers la boucle locale et de faux lanceurs de CLI :
**aucune** de ces injections ne se règle par ``poste.toml`` ni par l'environnement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .chemins import Emplacements, emplacements_du_compte
from .client_hermes import ClientHermes, OptionsClient
from .coffre import Coffre, CoffreDPAPI
from .inventaire import version_windows
from .journal import Journal
from .politique import Politique, compte_courant


@dataclass
class Contexte:
    emplacements: Emplacements
    coffre: Coffre
    options_client: OptionsClient = field(default_factory=OptionsClient)
    lanceurs: dict[str, list[str]] = field(default_factory=dict)
    environnement: dict[str, str] | None = None
    compte_courant: Callable[[], str] = compte_courant
    version_windows: Callable[[], str] = version_windows

    @classmethod
    def du_compte(cls) -> "Contexte":
        emplacements = emplacements_du_compte()
        return cls(emplacements=emplacements, coffre=CoffreDPAPI(emplacements.secrets))

    def journal(self, politique: Politique | None = None) -> Journal:
        if politique is None:
            return Journal(self.emplacements.journal)
        return Journal(self.emplacements.journal, taille_max_octets=politique.journal.taille_max_mo * 1024 * 1024,
                       fichiers=politique.journal.fichiers, niveau=politique.journal.niveau)

    def client(self, politique: Politique) -> ClientHermes:
        return ClientHermes(politique.hermes.origine, delai_connexion_s=politique.hermes.delai_connexion_s,
                            options=self.options_client)

    @property
    def racine_etat(self) -> Path:
        return self.emplacements.etat
