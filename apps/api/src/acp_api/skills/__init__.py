"""Bibliothèque de skills : sources d'import, scan indicatif, logique métier et catalogue.

Le contenu importé (``SKILL.md``, README, scripts) est une **donnée non fiable** : il est
borné, stocké tel quel et présenté comme du texte. Il ne modifie jamais une politique, un
droit ni une instruction système, et un skill de type ``native_plugin`` n'est jamais chargé
par la plateforme (simple étiquetage).

``SkillError`` est l'erreur commune des modules du package : elle porte le code HTTP à
renvoyer et un message en français destiné à l'utilisateur.
"""

from __future__ import annotations


class SkillError(Exception):
    """Refus métier de la bibliothèque de skills, avec le statut HTTP à renvoyer.

    ``status_code`` vaut 422 par défaut (contenu importé invalide) ; les modules utilisent
    aussi 403 (dossier non autorisé), 404 (introuvable), 409 (conflit d'état), 413 (limites
    dépassées), 502 (source distante en échec) et 503 (intégration non configurée).
    """

    def __init__(self, detail: str, *, status_code: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


__all__ = ["SkillError"]
