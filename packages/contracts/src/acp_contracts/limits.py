"""Bornes des valeurs acceptées à l'entrée, alignées sur ce que PostgreSQL stocke.

SQLite stocke des entiers de 64 bits, des textes de longueur quelconque et
l'octet NUL ; PostgreSQL refuse un entier hors de la plage de sa colonne
(``INTEGER`` : 32 bits, ``BIGINT`` : 64 bits), un texte plus long que son
``VARCHAR(n)`` et tout texte contenant ``\\x00``. Une valeur que seul PostgreSQL
refuserait est donc refusée ici, à la validation du contrat, avec un message
français : le même refus 422 sur les deux dialectes, avant toute écriture.

Les messages passent par ``ValueError`` : Pydantic les rend dans le détail du 422
(préfixés de « Value error, »), avec l'emplacement exact du champ fautif.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel, field_validator

INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

NUL = "\x00"
REPLACEMENT_CHARACTER = "�"
ELLIPSIS = "…"


def _integer_range(minimum: int, maximum: int, column: str):
    def check(value: int) -> int:
        if value < minimum or value > maximum:
            raise ValueError(
                f"valeur hors de la plage acceptée par la base ({column} : de "
                f"{minimum} à {maximum})"
            )
        return value

    return check


Int32 = Annotated[int, AfterValidator(_integer_range(INT32_MIN, INT32_MAX, "INTEGER"))]
"""Entier stocké dans une colonne ``INTEGER`` (32 bits signés sous PostgreSQL)."""

Int64 = Annotated[int, AfterValidator(_integer_range(INT64_MIN, INT64_MAX, "BIGINT"))]
"""Entier stocké dans une colonne ``BIGINT`` (64 bits signés).

C'est la borne d'un code de sortie : Windows rend un ``DWORD`` non signé
(``0xC000013A`` = 3221225786 après un CTRL_BREAK), POSIX un entier négatif pour
un signal ; les deux tiennent sur 64 bits signés, aucun ne tient sur 32.
"""


def refuse_nul(value: str) -> str:
    """Refuse un texte contenant l'octet NUL, que PostgreSQL ne sait pas stocker."""

    if NUL in value:
        raise ValueError(
            "le caractère NUL (\\x00) est interdit : la base de données ne peut pas "
            "le stocker"
        )
    return value


NulFreeStr = Annotated[str, AfterValidator(refuse_nul)]
"""Texte saisi par un utilisateur : un NUL y est refusé explicitement."""


def replace_nul(value: str) -> str:
    """Remplace chaque NUL par U+FFFD dans un texte capturé d'un programme.

    Réservé aux sorties machine (message d'erreur d'un test, extrait de journal) :
    refuser le lot entier pour un octet NUL perdrait tout le rapport. Le caractère
    de remplacement signale à la lecture qu'un octet non stockable était là ; rien
    n'est inventé ni retiré en silence.
    """

    return value.replace(NUL, REPLACEMENT_CHARACTER)


CapturedStr = Annotated[str, AfterValidator(replace_nul)]
"""Texte capturé d'un programme : chaque NUL devient U+FFFD."""



def captured_local_process_data(value):
    """Copie les deux textes capturés du runner local avant validation du DTO.

    Seuls stdout.text et stderr.text sont des sorties machine. Le manifeste,
    les autres champs et les empreintes restent inchangés ; les fichiers de
    preuve locaux et le dictionnaire fourni par le worker ne sont jamais mutés.
    L'appelant doit avoir vérifié le type de preuve ``local_process``.
    """
    if not isinstance(value, dict):
        return value
    result = dict(value)
    for stream_name in ("stdout", "stderr"):
        stream = value.get(stream_name)
        if isinstance(stream, dict) and isinstance(stream.get("text"), str):
            result[stream_name] = {**stream, "text": replace_nul(stream["text"])}
    return result


def captured_run_result(value):
    """Normalise la copie des preuves locales imbriquées dans un résultat de run.

    Une même preuve apparaît dans evidence et result.evidence sur le PATCH du
    worker. Aucun autre champ du résultat, aucune autre sorte de preuve et
    aucune entrée utilisateur ne sont normalisés ici.
    """
    if not isinstance(value, dict) or not isinstance(value.get("evidence"), list):
        return value
    evidence = []
    for item in value["evidence"]:
        if isinstance(item, dict) and item.get("kind") == "local_process":
            evidence.append({**item, "data": captured_local_process_data(item.get("data"))})
        else:
            evidence.append(item)
    return {**value, "evidence": evidence}


def bounded_label(max_chars: int):
    """Libellé d'affichage borné à ``max_chars`` caractères, NUL remplacé.

    Un libellé trop long (titre d'étape rédigé par un fournisseur de plan) est
    raccourci et se termine par « … », qui dit qu'il a été coupé : faire échouer une
    mission pour la longueur d'un intitulé serait disproportionné.
    """

    def shorten(value: str) -> str:
        value = replace_nul(value)
        if len(value) <= max_chars:
            return value
        return value[: max_chars - len(ELLIPSIS)] + ELLIPSIS

    return AfterValidator(shorten)


# Validation commune aux contrats qui transportent des données persistées.


def utc_datetime(value: datetime) -> datetime:
    """Normalise les instants conscients du fuseau et refuse un débordement UTC."""
    if value.tzinfo is None:
        return value
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError("horodatage hors de la plage UTC lisible (années 1 à 9999)") from exc


def _persistent_value(value):
    if isinstance(value, str):
        return refuse_nul(value)
    if isinstance(value, datetime):
        return utc_datetime(value)
    if isinstance(value, list):
        return [_persistent_value(item) for item in value]
    if isinstance(value, dict):
        return {_persistent_value(key): _persistent_value(item) for key, item in value.items()}
    return value


class DatabaseModel(BaseModel):
    """Refuse les NUL et les dates illisibles avant toute requête à la base."""

    @field_validator("*", mode="after")
    @classmethod
    def persistent_values(cls, value):
        return _persistent_value(value)


def text_limit(max_chars: int):
    """Borne française d'une colonne VARCHAR, commune aux deux dialectes."""
    def check(value: str) -> str:
        refuse_nul(value)
        if len(value) > max_chars:
            raise ValueError(f"texte trop long : au maximum {max_chars} caractères")
        return value
    return AfterValidator(check)


Text20 = Annotated[str, text_limit(20)]
Text36 = Annotated[str, text_limit(36)]
Text50 = Annotated[str, text_limit(50)]
Text100 = Annotated[str, text_limit(100)]
Text200 = Annotated[str, text_limit(200)]
Text300 = Annotated[str, text_limit(300)]
WorkflowLabel = Annotated[str, bounded_label(100)]
