"""Traduction des erreurs opérationnelles de la base en refus HTTP explicites.

Sous PostgreSQL, le moteur applique ``lock_timeout`` et ``statement_timeout``
(voir ``acp_database.engine``). Quand l'un d'eux tombe, psycopg lève une erreur
dont ``sqlstate`` vaut ``55P03`` (verrou indisponible) ou ``57014`` (requête
annulée par le délai). PostgreSQL annule aussi une transaction prise dans un
interblocage (``40P01``) ou un conflit de sérialisation (``40001``) : rien n'est
écrit et la requête peut être rejouée. Enfin, un pool sans connexion libre avant
``pool_timeout`` lève ``sqlalchemy.exc.TimeoutError``. Sans gestionnaire, l'API
répondrait 500 : ce module rend un 503 réessayable avec un message français, sans
jamais recopier le SQL, les paramètres de la requête ni l'URL de la base.

Toute autre ``OperationalError`` est relevée telle quelle : elle signale un défaut
que l'appelant ne peut pas corriger en réessayant, et le masquer en 503 serait un
faux diagnostic.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

LOCK_NOT_AVAILABLE = "55P03"
QUERY_CANCELED = "57014"
DEADLOCK_DETECTED = "40P01"
SERIALIZATION_FAILURE = "40001"

_MESSAGES = {
    LOCK_NOT_AVAILABLE: "Ressource temporairement verrouillée, réessayez",
    QUERY_CANCELED: "Requête interrompue par le délai maximal",
    # PostgreSQL a annulé cette transaction pour en laisser passer une autre : rien
    # n'a été écrit, la même requête peut être rejouée.
    DEADLOCK_DETECTED: "Conflit d'accès concurrent, rien n'a été enregistré : réessayez",
    SERIALIZATION_FAILURE: "Conflit d'accès concurrent, rien n'a été enregistré : réessayez",
}

POOL_EXHAUSTED_MESSAGE = "Service momentanément saturé : réessayez dans quelques secondes"


def sqlstate_of(exc: BaseException) -> str | None:
    """Code SQLSTATE porté par l'exception pilote, ou ``None`` (SQLite, autre pilote)."""

    origin = getattr(exc, "orig", None)
    state = getattr(origin, "sqlstate", None)
    return state if isinstance(state, str) else None


def response_for(exc: OperationalError) -> JSONResponse | None:
    """Réponse 503 pour un verrou ou un délai ; ``None`` pour tout autre cas."""

    message = _MESSAGES.get(sqlstate_of(exc) or "")
    if message is None:
        return None
    return JSONResponse(
        status_code=503,
        content={"detail": message},
        headers={"Cache-Control": "no-store", "Retry-After": "1"},
    )


def install(app: FastAPI) -> None:
    """Monte le gestionnaire d'``OperationalError`` sur ``app``.

    Le gestionnaire relève l'exception d'origine quand elle n'est ni un verrou ni
    un délai : Starlette la remonte alors à son gestionnaire d'erreurs serveur
    (500), exactement comme sans ce module.
    """

    async def handle_operational_error(
        _request: Request, exc: OperationalError
    ) -> JSONResponse:
        response = response_for(exc)
        if response is None:
            raise exc
        return response

    async def handle_pool_timeout(_request: Request, _exc: PoolTimeoutError) -> JSONResponse:
        # Aucune connexion libre dans le pool avant pool_timeout : saturation passagère,
        # pas un défaut de la requête. Le message ne cite ni la taille du pool ni l'URL.
        return JSONResponse(
            status_code=503,
            content={"detail": POOL_EXHAUSTED_MESSAGE},
            headers={"Cache-Control": "no-store", "Retry-After": "2"},
        )

    async def handle_data_error(_request: Request, _exc: DataError) -> JSONResponse:
        # Ne jamais reprendre le message du pilote : il contient le SQL et les données.
        return JSONResponse(
            status_code=422,
            content={"detail": "Valeur non stockable : vérifiez sa longueur, sa plage et l'absence de caractère NUL"},
            headers={"Cache-Control": "no-store"},
        )

    app.add_exception_handler(DataError, handle_data_error)
    app.add_exception_handler(OperationalError, handle_operational_error)
    app.add_exception_handler(PoolTimeoutError, handle_pool_timeout)
