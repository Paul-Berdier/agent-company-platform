"""Validation commune aux modèles du contrat : aucun NUL, aucun instant hors plage.

Repris de ``acp_contracts.limits`` (étiquette archive/acp-0.10.0-avant-hermes) sans
ce qui ne servait qu'à la base de données retirée. Un texte contenant l'octet NUL
est refusé, et un instant conscient du fuseau est ramené en UTC ou refusé s'il en
déborde : le même refus, en français, que le relevé vienne du poste ou du greffon.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, field_validator

NUL = "\x00"


def refuse_nul(value: str) -> str:
    """Refuse un texte contenant l'octet NUL.

    Le message nomme l'octet sous sa forme échappée ``\\x00`` : il ne doit jamais
    transporter l'octet qu'il refuse jusqu'aux journaux ou à une réponse 422.
    """

    if NUL in value:
        raise ValueError("le caractère NUL (\\x00) est interdit")
    return value


def utc_datetime(value: datetime) -> datetime:
    """Normalise les instants conscients du fuseau et refuse un débordement UTC."""

    if value.tzinfo is None:
        return value
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError("horodatage hors de la plage UTC lisible (années 1 à 9999)") from exc


def _valeur_valide(value):
    if isinstance(value, str):
        return refuse_nul(value)
    if isinstance(value, datetime):
        return utc_datetime(value)
    if isinstance(value, list):
        return [_valeur_valide(item) for item in value]
    if isinstance(value, dict):
        return {_valeur_valide(key): _valeur_valide(item) for key, item in value.items()}
    return value


class ContratValide(BaseModel):
    """Refuse les NUL et les dates illisibles dans tous les champs, à toute profondeur."""

    @field_validator("*", mode="after")
    @classmethod
    def valeurs_valides(cls, value):
        return _valeur_valide(value)
