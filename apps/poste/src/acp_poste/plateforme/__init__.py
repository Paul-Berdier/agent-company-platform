"""Couche plateforme du poste (cahier P6 § 7.1 et § 7.4, décision D76 : un seul paquet ``acp_poste``).

Le protocole ``acp-machine/1``, le contrat, le journal masqué, l'enrôlement, la présence, les sondes et le routage
sont communs ; seul ce qui dépend du système passe par une :class:`Plateforme` :

- **Windows** (:mod:`.windows`, poste P5) : dossiers connus du compte, coffre DPAPI, Job Object, bac à sable
  élevé de Codex. Le code reste où P5 l'a testé (``chemins``, ``coffre``, ``local_runner``, ``sondes_codex``) : la
  façade le désigne sans le recopier (écart au cahier § 7.4, qui parlait de « déplacement » : déplacer 900 lignes de
  ``ctypes`` sans changer leur effet n'apportait rien et aurait touché les tests P5).
- **Linux** (:mod:`.linux`, exécutant Railway) : dossiers sous ``/donnees``, secrets en fichiers 0600 de root, un
  UID par agent (``setpriv``), arrêt par groupe de processus puis par UID, sonde d'isolement.

Le choix se fait par ``sys.platform``, **jamais** par une variable d'environnement ni par la politique : une
variable modifiable par un exécutant mal confiné ne doit pas pouvoir faire passer le service d'un régime à l'autre.
L'option ``servir --plateforme`` n'est qu'une **assertion** (l'entrée de l'image la passe) : une valeur différente de
la plateforme réelle est refusée.
"""

from __future__ import annotations

import sys
from typing import Any, Protocol

NOMS = ("windows", "linux")


class PlateformeIndisponible(RuntimeError):
    """Système non pris en charge, ou plateforme annoncée différente de la plateforme réelle (message français)."""


class Plateforme(Protocol):
    """Ce que le reste du poste demande au système."""

    nom: str

    def emplacements(self) -> Any:
        """Emplacements réels de l'installation (jamais lus dans l'environnement)."""

    def coffre(self, emplacements: Any) -> Any:
        """Coffre des secrets de production (DPAPI sous Windows, fichiers 0600 de root sous Linux)."""

    def infos(self) -> dict[str, Any]:
        """``plateforme``, ``hote``, ``noyau`` et ``windows`` du bloc ``poste`` de l'inventaire (sans identifiant)."""


def nom_courant(plateforme_systeme: str | None = None) -> str:
    """« windows » ou « linux », d'après ``sys.platform`` seulement."""
    valeur = sys.platform if plateforme_systeme is None else plateforme_systeme
    if valeur == "win32":
        return "windows"
    if valeur.startswith("linux"):
        return "linux"
    raise PlateformeIndisponible(f"Système « {valeur} » non pris en charge par le poste : Windows ou Linux "
                                 "seulement.")


def verifier_annonce(annoncee: str | None, *, plateforme_systeme: str | None = None) -> str:
    """Plateforme réelle ; refus si ``annoncee`` (option ``--plateforme``) la contredit."""
    reelle = nom_courant(plateforme_systeme)
    if annoncee is not None and annoncee != reelle:
        raise PlateformeIndisponible(f"Plateforme annoncée « {annoncee} » différente de la plateforme réelle "
                                     f"« {reelle} » : refus de démarrer.")
    return reelle


def courante(plateforme_systeme: str | None = None) -> Plateforme:
    """La plateforme du système courant."""
    nom = nom_courant(plateforme_systeme)
    if nom == "windows":
        from .windows import PlateformeWindows

        return PlateformeWindows()
    from .linux import PlateformeLinux

    return PlateformeLinux()
