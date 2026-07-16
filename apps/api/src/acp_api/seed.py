"""Seed de démonstration : `python -m acp_api.seed`.

Crée une organisation, deux workspaces, quatre départements, quatre projets
multi-domaines, des équipes, des agents logiques et des tâches en file.
Idempotent : ne fait rien si l'organisation existe déjà.
"""

from acp_database import get_session_factory, init_db
from acp_database.models import (
    AgentInstanceModel,
    DepartmentModel,
    MembershipModel,
    MemoryModel,
    OrganizationModel,
    ProjectModel,
    ProviderModel,
    TaskModel,
    TeamMemberModel,
    TeamModel,
    WorkspaceModel,
)

ORG_NAME = "Virtual Company"

PROVIDERS = [
    ("orchestrator", "Mock Orchestrator", "mock"),
    ("orchestrator", "Manual Orchestrator", "manual"),
    ("orchestrator", "Hermes", "hermes"),
    ("execution", "Claude Code", "claude-code"),
    ("execution", "Codex CLI", "codex-cli"),
    ("execution", "Restricted Shell", "restricted-shell"),
    ("tool", "Git", "git"),
    ("tool", "Filesystem", "filesystem"),
    ("tool", "Blender MCP", "blender-mcp"),
    ("tool", "Unreal MCP", "unreal-mcp"),
    ("tool", "Browser", "browser"),
    ("tool", "Databases", "databases"),
    ("tool", "CI/CD", "cicd"),
]


def seed() -> bool:
    init_db()
    db = get_session_factory()()
    try:
        if db.query(OrganizationModel).filter_by(name=ORG_NAME).first():
            return False

        org = OrganizationModel(name=ORG_NAME, description="Entreprise virtuelle de démonstration")
        db.add(org)
        db.flush()

        ws_pro = WorkspaceModel(organization_id=org.id, name="Professionnel", kind="professionnel")
        ws_perso = WorkspaceModel(organization_id=org.id, name="Personnel", kind="personnel")
        db.add_all([ws_pro, ws_perso])
        db.flush()

        d_soft = DepartmentModel(workspace_id=ws_pro.id, name="Software Engineering",
                                 department_type="software-engineering", office_theme="dev-floor")
        d_data = DepartmentModel(workspace_id=ws_pro.id, name="Data Science",
                                 department_type="data-science", office_theme="data-lab")
        d_research = DepartmentModel(workspace_id=ws_perso.id, name="Research",
                                     department_type="research", office_theme="library")
        d_game = DepartmentModel(workspace_id=ws_perso.id, name="Game Development",
                                 department_type="game-development", office_theme="game-studio")
        db.add_all([d_soft, d_data, d_research, d_game])
        db.flush()

        projects = [
            ProjectModel(workspace_id=ws_pro.id, department_id=d_soft.id,
                         name="Plateforme Web", project_type="web-app",
                         description="Application web de gestion"),
            ProjectModel(workspace_id=ws_pro.id, department_id=d_data.id,
                         name="Pipeline Ventes", project_type="data-pipeline",
                         description="Pipeline data engineering des ventes"),
            ProjectModel(workspace_id=ws_perso.id, department_id=d_research.id,
                         name="Étude Agents LLM", project_type="research",
                         description="Projet de recherche sur les agents"),
            ProjectModel(workspace_id=ws_perso.id, department_id=d_game.id,
                         name="Prototype Jeu", project_type="game",
                         description="Prototype de jeu vidéo (module optionnel)"),
        ]
        db.add_all(projects)
        db.flush()
        p_web, p_data, p_research, p_game = projects

        teams = [
            TeamModel(project_id=p_web.id, name="Web Core Team", mission="Livrer le MVP web"),
            TeamModel(project_id=p_data.id, name="Data Squad", mission="Fiabiliser le pipeline"),
            TeamModel(project_id=p_research.id, name="Lab Team", mission="Publier l'étude"),
            TeamModel(project_id=p_game.id, name="Game Cell", mission="Prototype jouable"),
        ]
        db.add_all(teams)
        db.flush()
        t_web, t_data, t_research, t_game = teams

        agents_spec = [
            (ws_pro, t_web, "Alice", "frontend-developer", "software-development"),
            (ws_pro, t_web, "Bob", "backend-developer", "software-development"),
            (ws_pro, t_web, "Chloé", "qa-engineer", "software-development"),
            (ws_pro, t_data, "David", "data-engineer", "data-science"),
            (ws_pro, t_data, "Emma", "data-scientist", "data-science"),
            (ws_perso, t_research, "Farid", "researcher", "research"),
            (ws_perso, t_research, "Gaëlle", "research-assistant", "research"),
            (ws_perso, t_game, "Hugo", "game-designer", "game-development"),
            (ws_perso, t_game, "Inès", "gameplay-programmer", "game-development"),
        ]
        for ws, team, name, role, module in agents_spec:
            agent = AgentInstanceModel(workspace_id=ws.id, team_id=team.id,
                                       name=name, role_id=role, module=module)
            db.add(agent)
            db.flush()
            db.add(TeamMemberModel(team_id=team.id, agent_instance_id=agent.id, role_id=role))

        tasks_spec = [
            (p_web, t_web, "Mettre en place l'authentification", "queued", 1),
            (p_web, t_web, "Créer la page d'accueil", "queued", 2),
            (p_web, t_web, "Configurer le CI", "backlog", 3),
            (p_data, t_data, "Ingestion des ventes quotidiennes", "queued", 1),
            (p_data, t_data, "Nettoyage des données clients", "backlog", 2),
            (p_research, t_research, "Revue de littérature agents LLM", "queued", 2),
            (p_research, t_research, "Rédiger le protocole d'expérience", "backlog", 3),
            (p_game, t_game, "Game design document", "queued", 2),
            (p_game, t_game, "Prototype de déplacement", "backlog", 3),
        ]
        for project, team, title, status, priority in tasks_spec:
            db.add(TaskModel(project_id=project.id, team_id=team.id, title=title,
                             status=status, priority=priority))

        for ws in (ws_pro, ws_perso):
            db.add(MembershipModel(user_id="paul", scope_type="workspace",
                                   scope_id=ws.id, role="owner"))

        db.add_all([
            MemoryModel(scope="GLOBAL", owner_id=org.id, source="human",
                        classification="public", sharing_policy="shareable",
                        content={"note": "Convention de nommage : français pour l'UI, anglais pour le code."}),
            MemoryModel(scope="PROJECT", owner_id=p_web.id, source="human",
                        content={"note": "Stack cible : FastAPI + Vite."}),
            MemoryModel(scope="PROJECT", owner_id=p_data.id, source="human",
                        content={"note": "Les données ventes arrivent chaque nuit à 2h."}),
        ])

        for kind, name, key in PROVIDERS:
            db.add(ProviderModel(kind=kind, name=name, provider_key=key))

        db.commit()
        return True
    finally:
        db.close()


if __name__ == "__main__":
    created = seed()
    print("Seed appliqué." if created else "Seed déjà présent, rien à faire.")
