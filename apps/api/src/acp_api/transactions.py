"""Frontières de transaction autour des attentes réseau.

Sous PostgreSQL, le moteur applicatif pose ``idle_in_transaction_session_timeout``
(60 s, ``acp_database.engine``) : une session qui garde une transaction ouverte pendant
une attente réseau — réception d'un corps de requête, flux SSE, téléchargement, appel
sortant — est tuée par le serveur, et retient d'ici là une des connexions du pool. Une
dizaine d'attentes simultanées suffisaient à rendre toute l'API indisponible.

Règle : **aucune transaction ouverte pendant une attente réseau.** Les lectures de
contrôle (authentification, droits, bail) sont faites avant, puis leur transaction est
terminée ; ce qui doit être revérifié l'est après, sous verrou, dans une transaction
courte.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

__all__ = ["end_read_transaction"]


def end_read_transaction(db: Session) -> None:
    """Termine la transaction de lecture en cours et rend sa connexion au pool.

    Refuse (``RuntimeError``) s'il reste des écritures non validées : les annuler en
    silence perdrait des données, les valider ici masquerait un défaut de l'appelant,
    qui doit décider lui-même. Les objets chargés sont expirés et seront relus au
    prochain accès, dans une nouvelle transaction.
    """

    if db.new or db.dirty or db.deleted:
        raise RuntimeError(
            "Écritures non validées avant une attente réseau : validez-les ou "
            "annulez-les explicitement avant de libérer la transaction."
        )
    db.rollback()
