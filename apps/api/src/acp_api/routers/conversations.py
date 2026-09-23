"""Conversations persistantes et reprise idempotente des runs Hermes."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from acp_contracts import (
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationPatch,
    ConversationSummary,
    ConversationTurn,
    ConversationTurnCreate,
    ConversationTurnList,
)
from acp_database.models import ConversationModel, ConversationTurnModel, ProjectModel

from ..deps import ensure_access, get_auth_context, get_db, require_csrf
from ..gateway import GatewayClient, GatewayRun, GatewayUnavailableError, get_gateway_client
from ..security import AuthContext

router = APIRouter(prefix="/conversations", tags=["conversations"])

_ACTIVE_TURN_STATES = {"submitting", "running", "waiting_for_approval", "stopping"}
_RUNNING_PROVIDER_STATES = {
    "started",
    "queued",
    "running",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _summary(row: ConversationModel) -> ConversationSummary:
    return ConversationSummary.model_validate(row, from_attributes=True)


def _turn(row: ConversationTurnModel) -> ConversationTurn:
    return ConversationTurn.model_validate(row, from_attributes=True)


def _load_conversation(
    db: Session,
    conversation_id: str,
    context: AuthContext,
    *,
    minimum_role: str = "viewer",
) -> ConversationModel:
    conversation = db.get(ConversationModel, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    if conversation.project_id is None:
        if (
            conversation.created_by_user_id != context.user.id
            and context.user.platform_role != "owner"
        ):
            raise HTTPException(status_code=404, detail="Conversation introuvable")
    else:
        ensure_access(
            db,
            context.user.id,
            project_id=conversation.project_id,
            minimum_role=minimum_role,
        )
    return conversation


def _load_turn(
    db: Session,
    conversation: ConversationModel,
    turn_id: str,
) -> ConversationTurnModel:
    turn = (
        db.query(ConversationTurnModel)
        .filter_by(id=turn_id, conversation_id=conversation.id)
        .first()
    )
    if turn is None:
        raise HTTPException(status_code=404, detail="Message introuvable")
    return turn


def _write_turn_state(
    db: Session, conversation: ConversationModel, turn: ConversationTurnModel,
    expected_status: str, values: dict,
) -> None:
    """Écriture conditionnelle : une lecture tardive ne défait jamais un arrêt."""
    now = _now()
    changed = db.execute(
        update(ConversationTurnModel).where(
            ConversationTurnModel.id == turn.id,
            ConversationTurnModel.status == expected_status,
        ).values(**values, updated_at=now),
        execution_options={"synchronize_session": False},
    ).rowcount
    if changed:
        conversation.updated_at = now
    db.commit()
    db.refresh(turn)


def _apply_run(
    db: Session, conversation: ConversationModel, turn: ConversationTurnModel,
    run: GatewayRun, *, admission: bool = False,
) -> None:
    db.refresh(turn)
    if turn.status not in _ACTIVE_TURN_STATES:
        return
    expected_status = turn.status
    if turn.provider_run_id is not None and turn.provider_run_id != run.run_id:
        # Conserver le run connu et l'intention d'arrêt ; aucun état distant
        # n'a été prouvé par cette réponse destinée à un autre run.
        values = {"error": "Hermes a retourné l'identifiant d'un autre run."}
    else:
        values = {
            "provider_run_id": run.run_id,
            "provider_model": run.model or turn.provider_model or turn.requested_model,
            "usage": run.usage if run.usage is not None else turn.usage,
        }
        if run.status in _RUNNING_PROVIDER_STATES | {"waiting_for_approval", "stopping"}:
            if expected_status == "stopping" or run.status == "stopping":
                values.update(status="stopping", error=None)
            elif run.status == "waiting_for_approval":
                values.update(status="waiting_for_approval", error=(
                    "Hermes attend une approbation. La décision n'est pas disponible "
                    "dans cette interface ; vous pouvez arrêter ce tour."
                ))
            else:
                values.update(status="running", error=None)
        elif run.status == "completed":
            if run.output is None or not run.output.strip():
                # Un replay de POST peut être terminal sans contenir sa sortie.
                # GET doit relire le run, sans le requalifier prématurément en échec.
                if admission:
                    values.update(error="Hermes a terminé ; relecture de la réponse nécessaire.")
                else:
                    values.update(status="failed", error="Hermes a terminé le run sans réponse exploitable.")
            else:
                values.update(status="completed", assistant_content=run.output, error=None)
        elif run.status in {"cancelled", "interrupted"}:
            values.update(status="interrupted", error="Le run Hermes a été interrompu.")
        else:
            values.update(status="failed", error="Le run Hermes s'est terminé en erreur.")
    _write_turn_state(db, conversation, turn, expected_status, values)


async def _advance_turn(
    db: Session, conversation: ConversationModel, turn: ConversationTurnModel,
    client: GatewayClient,
) -> None:
    if turn.status not in _ACTIVE_TURN_STATES:
        return
    try:
        if turn.provider_run_id is None:
            created_at = turn.created_at.replace(tzinfo=timezone.utc) if turn.created_at.tzinfo is None else turn.created_at
            if _now() - created_at >= timedelta(hours=24):
                _write_turn_state(db, conversation, turn, turn.status, {"error": (
                    "L'admission reste indéterminée après la durée de conservation "
                    "de sa clé. Aucun nouveau run ne sera créé ; vérifiez le run dans Hermes."
                )})
                return
            run = await client.submit_hermes_run(
                prompt=turn.user_content, session_id=conversation.provider_session_id,
                idempotency_key=turn.idempotency_key, model=turn.requested_model,
                metadata={"conversation_id": conversation.id, "turn_id": turn.id,
                          "project_id": conversation.project_id},
            )
            _apply_run(db, conversation, turn, run, admission=True)
            # Un POST rejoué peut annoncer la fin sans inclure son résultat.
            if run.status == "completed" and turn.status in _ACTIVE_TURN_STATES:
                run = await client.get_hermes_run(run.run_id)
                _apply_run(db, conversation, turn, run)
        else:
            run = await client.get_hermes_run(turn.provider_run_id)
            _apply_run(db, conversation, turn, run)
        db.refresh(turn)
        if turn.status == "stopping" and turn.provider_run_id is not None:
            run = await client.stop_hermes_run(turn.provider_run_id)
            _apply_run(db, conversation, turn, run)
    except GatewayUnavailableError:
        db.refresh(turn)
        if turn.status not in _ACTIVE_TURN_STATES:
            return
        message = (
            "L'arrêt est enregistré mais n'est pas encore confirmé par Hermes. "
            "Il sera repris sur le même run."
            if turn.status == "stopping" else
            "Hermes est momentanément indisponible. Le message reste enregistré "
            "et sera repris avec la même clé d'idempotence."
        )
        _write_turn_state(db, conversation, turn, turn.status, {"error": message})


@router.get("", response_model=ConversationList)
def list_conversations(
    search: str | None = None,
    status: str | None = None,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    if status is not None and status not in {"active", "archived"}:
        raise HTTPException(status_code=422, detail="Statut de conversation inconnu")
    rows = db.query(ConversationModel).order_by(ConversationModel.updated_at.desc()).all()
    visible: list[ConversationSummary] = []
    for row in rows:
        try:
            _load_conversation(db, row.id, context)
        except HTTPException:
            continue
        if status is not None and row.status != status:
            continue
        if search is not None and search.strip().casefold() not in row.title.casefold():
            continue
        visible.append(_summary(row))
    return ConversationList(items=visible)


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(
    body: ConversationCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if body.project_id is not None:
        if db.get(ProjectModel, body.project_id) is None:
            raise HTTPException(status_code=404, detail="Projet introuvable")
        ensure_access(
            db,
            context.user.id,
            project_id=body.project_id,
            minimum_role="member",
        )
    title = (body.title or "").strip()
    if not title:
        title = "Conversation générale" if body.project_id is None else "Nouvelle conversation"
    conversation_id = str(uuid4())
    conversation = ConversationModel(
        id=conversation_id,
        project_id=body.project_id,
        created_by_user_id=context.user.id,
        title=title,
        status="active",
        provider_id="hermes",
        provider_session_id=f"acp-conversation-{conversation_id}",
    )
    db.add(conversation)
    db.commit()
    return _summary(conversation)


@router.patch("/{conversation_id}", response_model=ConversationSummary)
def patch_conversation(
    conversation_id: str,
    body: ConversationPatch,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    conversation = _load_conversation(
        db, conversation_id, context, minimum_role="member"
    )
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Le titre ne peut pas être vide")
        conversation.title = title
    if body.status is not None:
        conversation.status = body.status
    conversation.updated_at = _now()
    db.commit()
    return _summary(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    conversation = _load_conversation(db, conversation_id, context)
    turns = (
        db.query(ConversationTurnModel)
        .filter_by(conversation_id=conversation.id)
        .order_by(ConversationTurnModel.created_at.asc())
        .all()
    )
    return ConversationDetail(**_summary(conversation).model_dump(), turns=[_turn(t) for t in turns])


@router.get("/{conversation_id}/export")
def export_conversation(
    conversation_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    conversation = _load_conversation(db, conversation_id, context)
    turns = (
        db.query(ConversationTurnModel)
        .filter_by(conversation_id=conversation.id)
        .order_by(ConversationTurnModel.created_at.asc())
        .all()
    )
    detail = ConversationDetail(
        **_summary(conversation).model_dump(), turns=[_turn(turn) for turn in turns]
    )
    return JSONResponse(
        content=detail.model_dump(mode="json"),
        headers={
            "Content-Disposition": (
                f'attachment; filename="conversation-{conversation.id}.json"'
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{conversation_id}/turns", response_model=ConversationTurnList)
def list_conversation_turns(
    conversation_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
):
    conversation = _load_conversation(db, conversation_id, context)
    rows = (
        db.query(ConversationTurnModel)
        .filter_by(conversation_id=conversation.id)
        .order_by(ConversationTurnModel.created_at.asc())
        .all()
    )
    return ConversationTurnList(items=[_turn(row) for row in rows])


@router.post(
    "/{conversation_id}/turns",
    response_model=ConversationTurn,
    status_code=202,
)
async def create_conversation_turn(
    conversation_id: str,
    body: ConversationTurnCreate,
    context: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
    client: GatewayClient = Depends(get_gateway_client),
):
    conversation = _load_conversation(
        db, conversation_id, context, minimum_role="member"
    )
    if conversation.status != "active":
        raise HTTPException(status_code=409, detail="Cette conversation est archivée")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Le message ne peut pas être vide")
    existing = (
        db.query(ConversationTurnModel)
        .filter_by(
            conversation_id=conversation.id,
            client_request_id=body.client_request_id,
        )
        .first()
    )
    if existing is not None:
        if existing.user_content != content or existing.requested_model != body.model:
            raise HTTPException(
                status_code=409,
                detail="Cette clé de requête correspond déjà à un autre message",
            )
        await _advance_turn(db, conversation, existing, client)
        return _turn(existing)

    turn_id = str(uuid4())
    turn = ConversationTurnModel(
        id=turn_id,
        conversation_id=conversation.id,
        client_request_id=body.client_request_id,
        idempotency_key=f"acp-turn-{turn_id}",
        user_content=content,
        requested_model=body.model,
        provider_model=body.model,
        status="submitting",
    )
    db.add(turn)
    conversation.updated_at = _now()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(ConversationTurnModel)
            .filter_by(
                conversation_id=conversation.id,
                client_request_id=body.client_request_id,
            )
            .first()
        )
        if existing is None:
            raise HTTPException(
                status_code=409, detail="Le message existe déjà"
            ) from None
        if existing.user_content != content or existing.requested_model != body.model:
            raise HTTPException(
                status_code=409,
                detail="Cette clé de requête correspond déjà à un autre message",
            ) from None
        turn = existing
    await _advance_turn(db, conversation, turn, client)
    return _turn(turn)


@router.get(
    "/{conversation_id}/turns/{turn_id}",
    response_model=ConversationTurn,
)
async def get_conversation_turn(
    conversation_id: str,
    turn_id: str,
    context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    client: GatewayClient = Depends(get_gateway_client),
):
    conversation = _load_conversation(db, conversation_id, context)
    turn = _load_turn(db, conversation, turn_id)
    await _advance_turn(db, conversation, turn, client)
    return _turn(turn)


@router.post(
    "/{conversation_id}/turns/{turn_id}/stop",
    response_model=ConversationTurn, status_code=202,
)
async def stop_conversation_turn(
    conversation_id: str, turn_id: str,
    context: AuthContext = Depends(require_csrf), db: Session = Depends(get_db),
    client: GatewayClient = Depends(get_gateway_client),
):
    conversation = _load_conversation(db, conversation_id, context, minimum_role="member")
    turn = _load_turn(db, conversation, turn_id)
    # Le compare-and-set empêche un arrêt concurrent de réouvrir un état terminal.
    db.execute(update(ConversationTurnModel).where(
        ConversationTurnModel.id == turn.id,
        ConversationTurnModel.status.in_(_ACTIVE_TURN_STATES),
    ).values(status="stopping", error=None, updated_at=_now()),
        execution_options={"synchronize_session": False})
    db.commit()
    db.refresh(turn)
    await _advance_turn(db, conversation, turn, client)
    return _turn(turn)
