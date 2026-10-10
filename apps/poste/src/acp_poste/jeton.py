"""Jeton machine (``acpm_…``) et code d'enrôlement (``acpe_…``) du poste, jamais affichés (cahier P5 § 5.4).

En mémoire, un jeton est un objet au ``repr`` masqué (``Jeton(«masqué», empreinte=3F9A-0C1B)``) : il ne s'imprime,
ne se journalise ni ne se sérialise par mégarde. L'en-tête ``Authorization`` est construit à chaque requête
(:meth:`Jeton.en_tete`) ; la valeur n'entre jamais dans l'argv ni dans l'environnement d'un processus enfant.
Limite dite : une chaîne Python ne s'efface pas de la mémoire.

L'empreinte courte (``XXXX-XXXX``, 8 premiers caractères hexadécimaux du SHA-256) est celle que le propriétaire
compare sur la page Poste avant de confirmer le poste (décision D49) ; 32 bits d'un condensat ne révèlent rien
du jeton.
"""

from __future__ import annotations

import re

from acp_poste_contrat.machine import CODE_ENROLEMENT, JETON_MACHINE, empreinte_courte, empreinte_jeton


class JetonInvalide(ValueError):
    """Valeur au format invalide (le message ne la reprend jamais)."""


class _Secret:
    __slots__ = ("_valeur", "empreinte")
    _MOTIF: re.Pattern = JETON_MACHINE
    _NOM = "Jeton"

    def __init__(self, valeur: str) -> None:
        if not isinstance(valeur, str) or self._MOTIF.fullmatch(valeur) is None:
            raise JetonInvalide(f"{self._NOM} au format invalide.")
        self._valeur = valeur
        self.empreinte = empreinte_courte(empreinte_jeton(valeur))

    def __repr__(self) -> str:
        return f"{type(self).__name__}(«masqué», empreinte={self.empreinte})"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        return repr(self)

    def __reduce__(self):
        raise TypeError(f"{self._NOM} : sérialisation refusée.")

    def valeur_secrete(self) -> str:
        """La valeur, pour le coffre et l'en-tête HTTP seulement."""
        return self._valeur

    def en_tete(self) -> str:
        return f"Bearer {self._valeur}"


class Jeton(_Secret):
    """Jeton machine (256 bits) remis une fois par Hermes à l'enrôlement."""

    __slots__ = ()
    _MOTIF = JETON_MACHINE
    _NOM = "Jeton machine"


class CodeEnrolement(_Secret):
    """Code d'enrôlement à usage unique (10 min), collé par le propriétaire dans ``acp-poste enroler``."""

    __slots__ = ()
    _MOTIF = CODE_ENROLEMENT
    _NOM = "Code d'enrôlement"
