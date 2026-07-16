"""Tâches, task runs et endpoints du worker simulé."""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from acp_contracts import Event, SessionContext, Task, TaskRun
from acp_contracts.enums import SessionScope
from acp_database.models import (
    AgentInstanceModel,
    ProjectModel,
    SessionModel,
    TaskModel,
    TaskRunModel,
    TeamMemberModel,
    WorkspaceModel,
)

from ..deps import ensure_access, get_db, get_principal
from ..events_bus import forward_event, store_event

router = APIRouter(tags=["work"])


class TaskCreate(BaseModel):
    project_id: str
    team_id: str | None = None
    agent_instance_id: str | None = None
    title: str
    description: str = ""
    priority: int = 3
    meta: dict = Field(default_factory=dict)


class TaskPatch(BaseModel):
    status: str | None = None
    workflow_step: str | None = None
    agent_instance_id: str | None = None
    title: str | None = None
    description: str | None = None
    priority: int | None = None


class ClaimRequest(BaseModel):
    worker_id: str
    provider_id: str = "mock"


class TaskRunPatch(BaseModel):
    status: str | None = None
    plan: dict | None = None
    result: dict | None = None
    append_logs: list[dict] = Field(default_factory=list)


def _emit(db: Session, background: BackgroundTasks, event: Event) -> None:
    store_event(db, event)
    background.add_task(forward_event, event)


def _task_event_ids(db: Session, task: TaskModel) -> dict:
    project = db.get(ProjectModel, task.project_id)
    workspace = db.get(WorkspaceModel, project.workspace_id) if project else None
    return {
        "organization_id": workspace.organization_id if workspace else None,
        "workspace_id": project.workspace_id if project else None,
        "department_id": project.department_id if project else None,
        "project_id": task.project_id,
        "team_id": task.team_id,
        "agent_instance_id": task.agent_instance_id,
        "task_id": task.id,
    }


@router.post("/tasks", response_model=Task)
def create_task(
    body: TaskCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    principal: str | None = Depends(get_principal),
):
    ensure_access(db, principal, project_id=body.project_id, minimum_role="member")
    if db.get(ProjectModel, body.project_id) is None:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    obj = TaskModel(**body.model_dump())
    db.add(obj)
    db.commit()
    _emit(db, background, Event(type="task.created", **_task_event_ids(db, obj),
                                payload={"title": obj.title, "status": obj.status}))
    return Task.model_validate(obj, from_attributes=True)


@router.get("/tasks", response_model=list[Task])
def list_tasks(
    project_id: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(TaskModel)
    if project_id:
        q = q.filter_by(project_id=project_id)
    if status:
        q = q.filter_by(status=status)
    return [Task.model_validate(t, from_attributes=True) for t in q.all()]


@router.patch("/tasks/{task_id}", response_model=Task)
def patch_task(
    task_id: str,
    body: TaskPatch,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    task = db.get(TaskModel, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    changes = body.model_dump(exclude_none=True)
    status_changed = "status" in changes and changes["status"] != task.status
    for key, value in changes.items():
        setattr(task, key, value)
    db.commit()
    if status_changed:
        _emit(db, background, Event(type="task.status_changed", **_task_event_ids(db, task),
                                    payload={"status": task.status, "title": task.title,
                                             "workflow_step": task.workflow_step}))
    return Task.model_validate(task, from_attributes=True)


@router.post("/tasks/{task_id}/queue", response_model=Task)
def queue_task(task_id: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    task = db.get(TaskModel, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    task.status = "queued"
    db.commit()
    _emit(db, background, Event(type="task.queued", **_task_event_ids(db, task),
                                payload={"title": task.title}))
    return Task.model_validate(task, from_attributes=True)


@router.post("/worker/claim")
def claim_next_task(body: ClaimRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Attribue la prochaine tâche `queued` au worker, avec session d'exécution isolée."""
    task = (
        db.query(TaskModel)
        .filter_by(status="queued")
        .order_by(TaskModel.priority, TaskModel.created_at)
        .first()
    )
    if task is None:
        return {"task": None}

    project = db.get(ProjectModel, task.project_id)
    workspace = db.get(WorkspaceModel, project.workspace_id)

    agent = None
    if task.agent_instance_id:
        agent = db.get(AgentInstanceModel, task.agent_instance_id)
    if agent is None and task.team_id:
        member_ids = [
            m.agent_instance_id
            for m in db.query(TeamMemberModel).filter_by(team_id=task.team_id).all()
        ]
        if member_ids:
            candidates = (
                db.query(AgentInstanceModel)
                .filter(AgentInstanceModel.id.in_(member_ids))
                .all()
            )
            agent = next((a for a in candidates if a.status == "idle"), None) or candidates[0]
    if agent is None:
        agent = (
            db.query(AgentInstanceModel)
            .filter_by(workspace_id=project.workspace_id, status="idle")
            .first()
        )
    if agent is None:
        return {"task": None, "reason": "aucun agent disponible"}

    session = SessionModel(
        scope=SessionScope.AGENT_EXECUTION.value,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        project_id=project.id,
        team_id=task.team_id,
        agent_instance_id=agent.id,
        provider_id=body.provider_id,
        memory_scope="PROJECT",
    )
    run = TaskRunModel(
        task_id=task.id,
        agent_instance_id=agent.id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    task.status = "planning"
    task.agent_instance_id = agent.id
    agent.status = "thinking"
    db.add_all([session, run])
    db.commit()
    run.session_id = session.id
    db.commit()

    ids = _task_event_ids(db, task)
    _emit(db, background, Event(type="task.status_changed", **ids,
                                payload={"status": "planning", "title": task.title}))
    _emit(db, background, Event(
        type="agent.status_changed",
        organization_id=ids["organization_id"], workspace_id=ids["workspace_id"],
        department_id=ids["department_id"], project_id=ids["project_id"],
        team_id=task.team_id, agent_instance_id=agent.id,
        payload={"status": "thinking", "name": agent.name, "role_id": agent.role_id},
    ))

    context = SessionContext(
        session_id=session.id,
        scope=SessionScope.AGENT_EXECUTION,
        organization_id=workspace.organization_id,
        workspace_id=workspace.id,
        project_id=project.id,
        team_id=task.team_id,
        agent_instance_id=agent.id,
        provider_id=body.provider_id,
    )
    return {
        "task": Task.model_validate(task, from_attributes=True).model_dump(mode="json"),
        "task_run": TaskRun.model_validate(run, from_attributes=True).model_dump(mode="json"),
        "session": context.model_dump(mode="json"),
        "agent": {"id": agent.id, "name": agent.name, "role_id": agent.role_id},
        "project": {"id": project.id, "name": project.name, "project_type": project.project_type},
    }


@router.get("/task-runs", response_model=list[TaskRun])
def list_task_runs(task_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(TaskRunModel)
    if task_id:
        q = q.filter_by(task_id=task_id)
    return [TaskRun.model_validate(r, from_attributes=True) for r in q.all()]


@router.patch("/task-runs/{run_id}", response_model=TaskRun)
def patch_task_run(run_id: str, body: TaskRunPatch, db: Session = Depends(get_db)):
    run = db.get(TaskRunModel, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Task run introuvable")
    if body.status is not None:
        run.status = body.status
        if body.status in ("succeeded", "failed", "cancelled"):
            run.finished_at = datetime.now(timezone.utc)
    if body.plan is not None:
        run.plan = body.plan
    if body.result is not None:
        run.result = body.result
    if body.append_logs:
        run.logs = list(run.logs or []) + body.append_logs
    db.commit()
    return TaskRun.model_validate(run, from_attributes=True)
