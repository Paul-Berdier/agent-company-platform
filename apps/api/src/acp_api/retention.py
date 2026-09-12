"""Rétention du journal d'événements et des livrables (§5.5).

La commande est une **purge à blanc par défaut** : sans ``--apply``, elle décrit ce
qui disparaîtrait et ne touche rien. Une rétention est irréversible ; l'opérateur
doit pouvoir la lire avant de l'exécuter.

Deux protections ne se négocient pas :

1. **Les événements terminaux d'une tentative** (``task.completed``, ``task.failed``,
   …) survivent à toute échéance : sans eux, l'issue d'une mission n'est plus
   auditable.
2. **Les livrables cités par une preuve de mission** ne sont jamais effacés, qu'ils
   soient désignés par identifiant, par URI ou par empreinte.

Enfin, le stockage étant **adressé par contenu**, deux livrables distincts partagent
un même blob dès que leur contenu est identique. Supprimer le fichier parce qu'un
livrable expire viderait silencieusement l'autre : chaque blob n'est effacé qu'après
comptage des références encore vivantes.

Usage :

```text
python -m acp_api.retention              # purge à blanc (rien n'est supprimé)
python -m acp_api.retention --apply      # purge réelle
```
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TextIO

from sqlalchemy.orm import Session

from acp_database.models import ArtifactModel, EventModel, MissionEvidenceModel

from .artifacts_storage import (
    TEMP_DIRECTORY_NAME,
    ArtifactStorage,
    LocalArtifactStorage,
    local_artifact_storage,
)

EVENT_RETENTION_DAYS_ENV = "ACP_EVENT_RETENTION_DAYS"
ARTIFACT_RETENTION_DAYS_ENV = "ACP_ARTIFACT_RETENTION_DAYS"

DEFAULT_EVENT_RETENTION_DAYS = 90
DEFAULT_ARTIFACT_RETENTION_DAYS = 180

#: Âge au-delà duquel un fragment de téléversement interrompu est balayé.
TEMP_UPLOAD_MAX_AGE_HOURS = 24

#: Événements marquant la fin d'une tentative : jamais purgés.
TERMINAL_RUN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "task.completed",
        "task.failed",
        "task.blocked",
        "task.cancelled",
        "task.interrupted",
    }
)

#: Découpage d'une URI de preuve en jetons : un identifiant y est reconnu entier.
_URI_TOKENS = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True, slots=True)
class PurgeReport:
    """Ce qu'une purge a fait — ou ferait, quand ``applied`` est faux."""

    applied: bool
    event_days: int
    artifact_days: int
    events_deleted: int = 0
    events_protected: int = 0
    artifacts_marked: int = 0
    artifacts_protected: int = 0
    blobs_deleted: int = 0
    blobs_kept: int = 0
    stale_uploads_deleted: int = 0

    def summary(self) -> str:
        """Compte rendu français, lisible dans un journal d'exploitation."""

        mode = "Purge appliquée" if self.applied else "Purge à blanc (aucune suppression)"
        return (
            f"{mode} — événements supprimés : {self.events_deleted} "
            f"(conservés car terminaux : {self.events_protected}, "
            f"rétention {self.event_days} jours) ; "
            f"livrables marqués : {self.artifacts_marked} "
            f"(conservés car cités par une preuve : {self.artifacts_protected}, "
            f"rétention {self.artifact_days} jours) ; "
            f"blobs effacés : {self.blobs_deleted}, "
            f"blobs conservés car encore référencés : {self.blobs_kept} ; "
            f"fragments de téléversement balayés : {self.stale_uploads_deleted}."
        )


def retention_days(
    environ: Mapping[str, str], name: str, default: int
) -> int:
    """Durée de rétention en jours ; ``0`` signifie « illimité »."""

    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"{name} : un nombre de jours est attendu, « {raw} » a été lu."
        ) from exc
    if value < 0:
        raise ValueError(f"{name} : une durée négative n'a pas de sens.")
    return value


def _cited_artifact_ids_and_checksums(db: Session) -> tuple[set[str], set[str]]:
    """Identifiants et empreintes cités par une preuve de mission.

    Une preuve peut désigner un livrable de trois façons : un identifiant dans
    ``data``, une URI, ou l'empreinte du contenu. Les trois sont honorées — mieux
    vaut conserver un blob de trop que perdre une pièce justificative.
    """

    identifiers: set[str] = set()
    checksums: set[str] = set()
    for evidence in db.query(MissionEvidenceModel).all():
        data: Any = evidence.data or {}
        if isinstance(data, dict):
            single = data.get("artifact_id")
            if isinstance(single, str) and single:
                identifiers.add(single)
            many = data.get("artifact_ids")
            if isinstance(many, list):
                identifiers.update(item for item in many if isinstance(item, str))
        if evidence.uri:
            identifiers.update(
                token for token in _URI_TOKENS.split(evidence.uri) if token
            )
        if evidence.checksum:
            checksums.add(evidence.checksum)
    return identifiers, checksums


def _sweep_stale_uploads(
    storage: ArtifactStorage, *, now: datetime, apply: bool
) -> int:
    """Balaie les ``.part`` abandonnés par un téléversement interrompu.

    Ces fragments ne sont jamais servis (leur nom n'a pas la forme d'une clé), mais
    ils occupent le disque tant que personne ne les retire.
    """

    root = getattr(storage, "root", None)
    if not isinstance(root, Path):
        return 0
    temporary = root / TEMP_DIRECTORY_NAME
    if not temporary.is_dir():
        return 0
    cutoff = (now - timedelta(hours=TEMP_UPLOAD_MAX_AGE_HOURS)).timestamp()
    swept = 0
    for fragment in temporary.glob("upload-*.part"):
        try:
            if fragment.stat().st_mtime >= cutoff:
                continue
        except OSError:  # pragma: no cover - fichier disparu entre-temps
            continue
        swept += 1
        if apply:
            try:
                fragment.unlink()
            except OSError:  # pragma: no cover - verrou Windows transitoire
                swept -= 1
    return swept


def purge_expired(
    db: Session,
    storage: ArtifactStorage,
    *,
    event_days: int | None = None,
    artifact_days: int | None = None,
    now: datetime | None = None,
    apply: bool = False,
) -> PurgeReport:
    """Applique — ou simule — la rétention du journal et des livrables.

    Sans ``apply=True``, rien n'est écrit ni effacé : le rapport décrit ce qui
    disparaîtrait. C'est le mode par défaut, volontairement.
    """

    moment = now or datetime.now(timezone.utc)
    if event_days is None:
        event_days = retention_days(
            os.environ, EVENT_RETENTION_DAYS_ENV, DEFAULT_EVENT_RETENTION_DAYS
        )
    if artifact_days is None:
        artifact_days = retention_days(
            os.environ, ARTIFACT_RETENTION_DAYS_ENV, DEFAULT_ARTIFACT_RETENTION_DAYS
        )
    if event_days < 0 or artifact_days < 0:
        raise ValueError("Une durée de rétention négative n'a pas de sens.")

    events_deleted = 0
    events_protected = 0
    if event_days > 0:
        cutoff = moment - timedelta(days=event_days)
        terminal = sorted(TERMINAL_RUN_EVENT_TYPES)
        expired = db.query(EventModel).filter(EventModel.occurred_at < cutoff)
        # Compté et supprimé en base : un journal de plusieurs millions de lignes ne
        # doit pas transiter par la mémoire du processus de maintenance.
        events_protected = expired.filter(EventModel.type.in_(terminal)).count()
        deletable = expired.filter(EventModel.type.notin_(terminal))
        events_deleted = deletable.count()
        if apply and events_deleted:
            deletable.delete(synchronize_session=False)

    artifacts_marked = 0
    artifacts_protected = 0
    blobs_deleted = 0
    blobs_kept = 0
    orphaned: list[str] = []
    if artifact_days > 0:
        cutoff = moment - timedelta(days=artifact_days)
        cited_ids, cited_checksums = _cited_artifact_ids_and_checksums(db)
        expired = (
            db.query(ArtifactModel)
            .filter(
                ArtifactModel.created_at < cutoff,
                ArtifactModel.deleted_at.is_(None),
            )
            .all()
        )
        doomed: list[ArtifactModel] = []
        for artifact in expired:
            if artifact.id in cited_ids or (
                artifact.checksum and artifact.checksum in cited_checksums
            ):
                artifacts_protected += 1
                continue
            doomed.append(artifact)
        artifacts_marked = len(doomed)
        # Comptage de références : un blob n'est effacé que si les livrables encore
        # vivants qui le désignent sont **tous** dans la fournée condamnée. La
        # comparaison se fait sur des compteurs plutôt que sur une clause ``NOT IN``
        # : une purge annuelle peut condamner bien plus de lignes qu'un moteur
        # n'accepte de paramètres.
        doomed_by_key = Counter(
            artifact.storage_key for artifact in doomed if artifact.storage_key
        )
        for key, condemned in sorted(doomed_by_key.items()):
            live = (
                db.query(ArtifactModel.id)
                .filter(
                    ArtifactModel.storage_key == key,
                    ArtifactModel.deleted_at.is_(None),
                )
                .count()
            )
            if live > condemned:
                blobs_kept += 1
                continue
            orphaned.append(key)
        blobs_deleted = len(orphaned)
        if apply:
            for artifact in doomed:
                artifact.deleted_at = moment

    if apply:
        # La base d'abord, les fichiers ensuite : si le commit échoue, aucun blob
        # n'a disparu sous une ligne qui le désigne encore. L'inverse laisserait un
        # livrable « présent » dont le contenu n'existe plus.
        db.commit()
        for key in orphaned:
            storage.delete(key)
    else:
        db.rollback()

    return PurgeReport(
        applied=apply,
        event_days=event_days,
        artifact_days=artifact_days,
        events_deleted=events_deleted,
        events_protected=events_protected,
        artifacts_marked=artifacts_marked,
        artifacts_protected=artifacts_protected,
        blobs_deleted=blobs_deleted,
        blobs_kept=blobs_kept,
        stale_uploads_deleted=_sweep_stale_uploads(storage, now=moment, apply=apply),
    )


# --- Commande -------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m acp_api.retention",
        description=(
            "Applique la rétention du journal d'événements et des livrables. "
            "Sans --apply, rien n'est supprimé."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Effectue réellement la purge (sinon, purge à blanc).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Purge à blanc explicite (comportement par défaut).",
    )
    parser.add_argument(
        "--event-days",
        type=int,
        default=None,
        help="Rétention des événements en jours (0 = illimité).",
    )
    parser.add_argument(
        "--artifact-days",
        type=int,
        default=None,
        help="Rétention des contenus de livrables en jours (0 = illimité).",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Any | None = None,
    storage: ArtifactStorage | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Point d'entrée de la commande ; renvoie 0 en succès, 2 en usage invalide."""

    out = stdout or sys.stdout
    err = stderr or sys.stderr
    parser = _parser()
    try:
        arguments = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit:  # pragma: no cover - argparse a déjà expliqué
        return 2
    if arguments.apply and arguments.dry_run:
        print(
            "Choisissez --apply ou --dry-run, pas les deux : la purge réelle doit "
            "être demandée sans ambiguïté.",
            file=err,
        )
        return 2
    for name, value in (
        ("--event-days", arguments.event_days),
        ("--artifact-days", arguments.artifact_days),
    ):
        if value is not None and value < 0:
            print(f"{name} : une durée négative n'a pas de sens.", file=err)
            return 2

    if session_factory is None:  # pragma: no cover - chemin de production
        from acp_database import get_session_factory, init_db

        init_db()
        session_factory = get_session_factory()
    blob_storage: ArtifactStorage = storage or _default_storage()
    try:
        with session_factory() as db:
            report = purge_expired(
                db,
                blob_storage,
                event_days=arguments.event_days,
                artifact_days=arguments.artifact_days,
                apply=arguments.apply,
            )
    except ValueError as exc:
        print(str(exc), file=err)
        return 2
    print(report.summary(), file=out)
    if not report.applied:
        print(
            "Relancez avec --apply pour exécuter réellement cette purge.", file=out
        )
    return 0


def _default_storage() -> LocalArtifactStorage:  # pragma: no cover - production
    return local_artifact_storage(os.environ)


if __name__ == "__main__":  # pragma: no cover - utilitaire de console
    raise SystemExit(main(sys.argv[1:]))
