"""Contexte d'exécution d'une commande ``acp-poste`` : plateforme, emplacements, coffre, compte, injections de test.

En production, :meth:`Contexte.du_compte` demande tout à la plateforme du système (:mod:`acp_poste.plateforme`,
choisie par ``sys.platform``) : sous Windows, les dossiers connus du compte courant et le coffre DPAPI ; sous Linux
(exécutant Railway), les dossiers de ``/donnees``, le coffre en fichiers 0600 de root, et un lanceur par agent
(``setpriv`` vers son UID dédié) avec un environnement calculé. Les tests et le bout en bout local
(``apps/poste/tests/e2e/lancer_poste.py``) construisent un contexte sur une racine jetable, avec une autorité de test,
une résolution forcée vers la boucle locale et de faux lanceurs de CLI : **aucune** de ces injections ne se règle par
la politique ni par l'environnement.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from .client_hermes import ClientHermes, OptionsClient
from .coffre import Coffre
from .inventaire import version_windows
from .journal import Journal
from .politique import Politique, compte_courant

OUTILS_AGENTS = {"codex": "acp-codex", "claude": "acp-claude"}


@dataclass
class Contexte:
    emplacements: Any
    coffre: Coffre
    options_client: OptionsClient = field(default_factory=OptionsClient)
    lanceurs: dict[str, list[str]] = field(default_factory=dict)
    environnement: dict[str, str] | None = None
    compte_courant: Callable[[], str] = compte_courant
    version_windows: Callable[[], str] = version_windows
    plateforme: str = "windows"
    # Linux : identité (UID) de chaque outil ; ``None`` sous Windows (un seul compte, ``acp-poste``). Les tests sous
    # Linux sans root la laissent vide : les faux CLI tournent alors sous le compte du test.
    identites: dict[str, Any] = field(default_factory=dict)
    infos_plateforme: Callable[[], dict[str, Any]] | None = None

    @classmethod
    def du_compte(cls) -> "Contexte":
        from . import plateforme

        systeme = plateforme.courante()
        emplacements = systeme.emplacements()
        if systeme.nom == "windows":
            return cls(emplacements=emplacements, coffre=systeme.coffre(emplacements))
        from .plateforme.linux import IDENTITES

        return cls(emplacements=emplacements, coffre=systeme.coffre(emplacements), plateforme="linux",
                   identites={outil: IDENTITES[nom] for outil, nom in OUTILS_AGENTS.items()},
                   infos_plateforme=systeme.infos)

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

    # ------------------------------------------------------------------ plateforme
    def infos(self) -> dict[str, Any]:
        """Bloc ``plateforme``/``hote``/``noyau``/``windows`` de l'inventaire."""
        if self.infos_plateforme is not None:
            return self.infos_plateforme()
        return {"plateforme": "windows", "hote": "pc", "noyau": None, "windows": self.version_windows()}

    def lanceurs_pour(self, politique: Politique) -> dict[str, list[str]]:
        """argv de lancement de chaque CLI. Injection de test d'abord ; sous Linux, ``setpriv`` vers l'UID de l'outil
        devant l'exécutable de la politique — seulement s'il existe (absent : la sonde dit « CLI absente »)."""
        lanceurs = dict(self.lanceurs)
        for outil, section in (("codex", politique.codex), ("claude", politique.claude)):
            if outil in lanceurs or section is None or outil not in self.identites:
                continue
            if section.executable.is_file():
                from .plateforme.linux import prefixe_setpriv

                lanceurs[outil] = [*prefixe_setpriv(self.identites[outil]), str(section.executable)]
        return lanceurs

    def environnement_pour(self, outil: str) -> dict[str, str] | None:
        """Environnement SOURCE des sondes d'un outil (les sondes en retiennent une liste blanche). Sous Linux, celui
        de son identité (``HOME`` de l'agent, ``PATH`` minimal), jamais celui du superviseur."""
        if outil in self.identites:
            from .plateforme.linux import environnement_agent

            return environnement_agent(self.identites[outil])
        return self.environnement

    def environnements(self) -> dict[str, dict[str, str] | None]:
        return {outil: self.environnement_pour(outil) for outil in ("codex", "claude")}

    def dossiers_pour(self, outil: str) -> Callable[..., contextlib.AbstractContextManager[str]] | None:
        """Fabrique de dossiers temporaires des sondes d'un outil : sous Linux, propriété de l'UID de l'outil (le
        processus de l'agent doit pouvoir y entrer et y écrire) ; ``None`` ailleurs (``TemporaryDirectory``)."""
        if outil not in self.identites:
            return None
        ident = self.identites[outil]
        racine = Path(self.emplacements.tmp) / "sondes"

        @contextlib.contextmanager
        def fabrique(prefix: str = "acp-sonde-", **_ignore: Any) -> Iterator[str]:
            racine.mkdir(parents=True, exist_ok=True)
            dossier = tempfile.mkdtemp(prefix=prefix, dir=racine)
            try:
                os.chown(dossier, ident.uid, ident.gid)
                os.chmod(dossier, 0o700)
                yield dossier
            finally:
                shutil.rmtree(dossier, ignore_errors=True)

        return fabrique
