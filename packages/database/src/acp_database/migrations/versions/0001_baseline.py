"""Schéma de référence : les 47 tables du modèle 0.8.0, telles que create_all() les produit.

Révision : 0001
Précédente : aucune

DDL explicite figé, généré par autogénération contre une base PostgreSQL vide
puis relu et fixé à la main : ``UtcDateTime`` est rendu par son implémentation
``DateTime(timezone=True)``, les noms d'index et de contraintes sont ceux du
modèle (les 3 UNIQUE et 88 FOREIGN KEY anonymes restent anonymes), les
booléens sont des ``Integer`` bornés par CHECK, ``JSON`` reste générique. Les
deux index uniques partiels ``uq_event_run_sequence`` et ``uq_events_journal_seq``
portent ces noms exacts : ``events_bus`` les lit dans les erreurs d'intégrité
pour reconnaître une collision d'allocation.

La clé étrangère circulaire ``tasks.active_run_id -> task_runs.id`` est écrite
en ligne sous SQLite (pas d'``ALTER TABLE … ADD CONSTRAINT``) et ajoutée après
``task_runs`` par ``ALTER`` sur les autres dialectes, comme le fait
``create_all()``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _tasks_active_run_foreign_key() -> list:
    """Clé circulaire en ligne sous SQLite seulement (voir l'en-tête du module)."""

    if _is_sqlite():
        return [sa.ForeignKeyConstraint(["active_run_id"], ["task_runs.id"])]
    return []


def upgrade() -> None:
    op.create_table('events',
    sa.Column('type', sa.String(length=100), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=True),
    sa.Column('workspace_id', sa.String(length=36), nullable=True),
    sa.Column('department_id', sa.String(length=36), nullable=True),
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('team_id', sa.String(length=36), nullable=True),
    sa.Column('agent_instance_id', sa.String(length=36), nullable=True),
    sa.Column('task_id', sa.String(length=36), nullable=True),
    sa.Column('task_run_id', sa.String(length=36), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('schema_version', sa.String(length=10), server_default='1.0', nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=True),
    sa.Column('journal_seq', sa.Integer(), nullable=True),
    sa.Column('conversation_id', sa.String(length=36), nullable=True),
    sa.Column('step_id', sa.String(length=64), nullable=True),
    sa.Column('executor', sa.String(length=64), nullable=True),
    sa.Column('emitted_by', sa.String(length=64), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_events_conversation_id', 'events', ['conversation_id'], unique=False)
    op.create_index('ix_events_journal_seq', 'events', ['journal_seq'], unique=False)
    op.create_index('ix_events_project_id', 'events', ['project_id'], unique=False)
    op.create_index('ix_events_task_run_sequence', 'events', ['task_run_id', 'sequence'], unique=False)
    op.create_index('ix_events_type', 'events', ['type'], unique=False)
    op.create_index('uq_event_run_sequence', 'events', ['task_run_id', 'sequence'], unique=True, sqlite_where=sa.text('task_run_id IS NOT NULL AND sequence IS NOT NULL'), postgresql_where=sa.text('task_run_id IS NOT NULL AND sequence IS NOT NULL'))
    op.create_index('uq_events_journal_seq', 'events', ['journal_seq'], unique=True, sqlite_where=sa.text('journal_seq IS NOT NULL'), postgresql_where=sa.text('journal_seq IS NOT NULL'))
    op.create_table('memberships',
    sa.Column('user_id', sa.String(length=200), nullable=False),
    sa.Column('scope_type', sa.String(length=50), nullable=False),
    sa.Column('scope_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=50), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_memberships_scope_id', 'memberships', ['scope_id'], unique=False)
    op.create_index('ix_memberships_user_id', 'memberships', ['user_id'], unique=False)
    op.create_table('memories',
    sa.Column('scope', sa.String(length=50), nullable=False),
    sa.Column('owner_id', sa.String(length=36), nullable=False),
    sa.Column('source', sa.String(length=200), nullable=False),
    sa.Column('classification', sa.String(length=50), nullable=False),
    sa.Column('sharing_policy', sa.String(length=50), nullable=False),
    sa.Column('ttl_seconds', sa.Integer(), nullable=True),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_memories_owner_id', 'memories', ['owner_id'], unique=False)
    op.create_index('ix_memories_scope', 'memories', ['scope'], unique=False)
    op.create_table('organizations',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('providers',
    sa.Column('kind', sa.String(length=50), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('provider_key', sa.String(length=100), nullable=False),
    sa.Column('contract_version', sa.String(length=20), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('enabled', sa.Integer(), nullable=False),
    sa.Column('last_latency_ms', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_key')
    )
    op.create_table('sessions',
    sa.Column('scope', sa.String(length=50), nullable=False),
    sa.Column('organization_id', sa.String(length=36), nullable=True),
    sa.Column('workspace_id', sa.String(length=36), nullable=True),
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('team_id', sa.String(length=36), nullable=True),
    sa.Column('agent_instance_id', sa.String(length=36), nullable=True),
    sa.Column('provider_id', sa.String(length=100), nullable=True),
    sa.Column('external_session_id', sa.String(length=200), nullable=True),
    sa.Column('memory_scope', sa.String(length=50), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('login_normalized', sa.String(length=254), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('platform_role', sa.String(length=50), nullable=False),
    sa.Column('is_active', sa.Integer(), nullable=False),
    sa.Column('bootstrap_marker', sa.String(length=32), nullable=True),
    sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bootstrap_marker')
    )
    op.create_index('ix_users_login_normalized', 'users', ['login_normalized'], unique=True)
    op.create_index('ix_users_platform_role', 'users', ['platform_role'], unique=False)
    op.create_table('skills',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('source_kind', sa.String(length=20), nullable=False),
    sa.Column('origin', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('current_revision_id', sa.String(length=36), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_reason', sa.Text(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_skills_created_by_user_id', 'skills', ['created_by_user_id'], unique=False)
    op.create_index('ix_skills_name', 'skills', ['name'], unique=True)
    op.create_index('ix_skills_status', 'skills', ['status'], unique=False)
    op.create_table('user_sessions',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token_hash', sa.String(length=64), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_user_sessions_expires_at', 'user_sessions', ['expires_at'], unique=False)
    op.create_index('ix_user_sessions_revoked_at', 'user_sessions', ['revoked_at'], unique=False)
    op.create_index('ix_user_sessions_token_hash', 'user_sessions', ['token_hash'], unique=True)
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'], unique=False)
    op.create_table('workspaces',
    sa.Column('organization_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=50), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('departments',
    sa.Column('workspace_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('department_type', sa.String(length=100), nullable=False),
    sa.Column('office_theme', sa.String(length=100), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('skill_revisions',
    sa.Column('skill_id', sa.String(length=36), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('files', sa.JSON(), nullable=False),
    sa.Column('skill_md', sa.Text(), nullable=False),
    sa.Column('frontmatter', sa.JSON(), nullable=False),
    sa.Column('license', sa.String(length=120), nullable=True),
    sa.Column('dependencies', sa.JSON(), nullable=False),
    sa.Column('scan', sa.JSON(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('storage_path', sa.String(length=1000), nullable=False),
    sa.Column('change_summary', sa.JSON(), nullable=False),
    sa.Column('requires_approval', sa.Integer(), nullable=False),
    sa.Column('approved_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approval_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_ref', sa.String(length=500), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['approved_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('skill_id', 'number', name='uq_skill_revision_number')
    )
    op.create_index('ix_skill_revisions_fingerprint', 'skill_revisions', ['fingerprint'], unique=False)
    op.create_index('ix_skill_revisions_skill_id', 'skill_revisions', ['skill_id'], unique=False)
    op.create_table('projects',
    sa.Column('workspace_id', sa.String(length=36), nullable=False),
    sa.Column('department_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('project_type', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('automations',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('schedule_kind', sa.String(length=20), nullable=False),
    sa.Column('schedule_expression', sa.String(length=200), nullable=False),
    sa.Column('timezone', sa.String(length=64), server_default='Europe/Paris', nullable=False),
    sa.Column('mission_template', sa.JSON(), nullable=False),
    sa.Column('enabled', sa.Integer(), server_default='0', nullable=False),
    sa.Column('catchup_policy', sa.String(length=20), server_default='skip', nullable=False),
    sa.Column('max_concurrent_runs', sa.Integer(), server_default='1', nullable=False),
    sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_fire_key', sa.String(length=64), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('create_idempotency_key', sa.String(length=200), nullable=True),
    sa.Column('create_request_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('webhook_enabled', sa.Integer(), server_default='0', nullable=False),
    sa.Column('webhook_secret_hash', sa.String(length=64), nullable=True),
    sa.Column('webhook_rotated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('webhook_rotation_number', sa.Integer(), server_default='0', nullable=False),
    sa.Column('consecutive_failures', sa.Integer(), server_default='0', nullable=False),
    sa.Column('failure_threshold', sa.Integer(), server_default='3', nullable=False),
    sa.Column('mutation_revision', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('(create_idempotency_key IS NULL AND create_request_fingerprint IS NULL) OR (create_idempotency_key IS NOT NULL AND create_request_fingerprint IS NOT NULL AND created_by_user_id IS NOT NULL)', name='ck_automations_create_idempotency_complete'),
    sa.CheckConstraint('consecutive_failures >= 0', name='ck_automations_consecutive_failures'),
    sa.CheckConstraint('failure_threshold >= 1', name='ck_automations_failure_threshold'),
    sa.CheckConstraint('mutation_revision >= 0', name='ck_automations_mutation_revision'),
    sa.CheckConstraint('webhook_rotation_number >= 0', name='ck_automations_webhook_rotation_number'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'created_by_user_id', 'create_idempotency_key', name='uq_automations_create_principal_key')
    )
    op.create_index('ix_automations_created_by_user_id', 'automations', ['created_by_user_id'], unique=False)
    op.create_index('ix_automations_next_run_at', 'automations', ['next_run_at'], unique=False)
    op.create_index('ix_automations_project_id', 'automations', ['project_id'], unique=False)
    op.create_table('conversations',
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('provider_id', sa.String(length=100), nullable=False),
    sa.Column('provider_session_id', sa.String(length=200), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversations_created_by_user_id', 'conversations', ['created_by_user_id'], unique=False)
    op.create_index('ix_conversations_project_id', 'conversations', ['project_id'], unique=False)
    op.create_index('ix_conversations_provider_session_id', 'conversations', ['provider_session_id'], unique=True)
    op.create_index('ix_conversations_status', 'conversations', ['status'], unique=False)
    op.create_index('ix_conversations_updated_at', 'conversations', ['updated_at'], unique=False)
    op.create_table('notification_preferences',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('channel', sa.String(length=20), server_default='in_app', nullable=False),
    sa.Column('enabled', sa.Integer(), server_default='1', nullable=False),
    sa.Column('minimum_severity', sa.String(length=20), server_default='warning', nullable=False),
    sa.Column('budget_alerts', sa.Integer(), server_default='1', nullable=False),
    sa.Column('automation_failures', sa.Integer(), server_default='1', nullable=False),
    sa.Column('storage_alerts', sa.Integer(), server_default='1', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("channel = 'in_app'", name='ck_notification_preferences_channel'),
    sa.CheckConstraint("minimum_severity IN ('info', 'warning', 'critical')", name='ck_notification_preferences_minimum_severity'),
    sa.CheckConstraint('automation_failures IN (0, 1)', name='ck_notification_preferences_automation'),
    sa.CheckConstraint('budget_alerts IN (0, 1)', name='ck_notification_preferences_budget'),
    sa.CheckConstraint('enabled IN (0, 1)', name='ck_notification_preferences_enabled'),
    sa.CheckConstraint('storage_alerts IN (0, 1)', name='ck_notification_preferences_storage'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'user_id', name='uq_notification_preferences_project_user')
    )
    op.create_index('ix_notification_preferences_project_id', 'notification_preferences', ['project_id'], unique=False)
    op.create_index('ix_notification_preferences_user_id', 'notification_preferences', ['user_id'], unique=False)
    op.create_table('project_budget_policies',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('timezone', sa.String(length=64), server_default='Europe/Paris', nullable=False),
    sa.Column('policy', sa.JSON(), server_default='{}', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('length(timezone) > 0', name='ck_project_budget_timezone_nonempty'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', name='uq_project_budget_policies_project')
    )
    op.create_index('ix_project_budget_policies_project_id', 'project_budget_policies', ['project_id'], unique=False)
    op.create_table('secrets',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('scope_type', sa.String(length=20), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('key_id', sa.String(length=16), nullable=False),
    sa.Column('ciphertext', sa.Text(), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', 'scope_type', 'project_id', name='uq_secret_name_scope_project')
    )
    op.create_index('ix_secrets_created_by_user_id', 'secrets', ['created_by_user_id'], unique=False)
    op.create_index('ix_secrets_name', 'secrets', ['name'], unique=False)
    op.create_index('ix_secrets_project_id', 'secrets', ['project_id'], unique=False)
    op.create_index('ix_secrets_revoked_at', 'secrets', ['revoked_at'], unique=False)
    op.create_table('skill_bindings',
    sa.Column('skill_id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('revision_id', sa.String(length=36), nullable=False),
    sa.Column('enabled', sa.Integer(), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['revision_id'], ['skill_revisions.id'], ),
    sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('skill_id', 'project_id', name='uq_skill_binding_skill_project')
    )
    op.create_index('ix_skill_bindings_project_id', 'skill_bindings', ['project_id'], unique=False)
    op.create_index('ix_skill_bindings_skill_id', 'skill_bindings', ['skill_id'], unique=False)
    op.create_table('teams',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('mission', sa.Text(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('workers',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('token_prefix', sa.String(length=12), nullable=False),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('capabilities', sa.JSON(), nullable=False),
    sa.Column('max_concurrency', sa.Integer(), nullable=False),
    sa.Column('active_runs', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('simulation', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('global_access', sa.Integer(), nullable=False),
    sa.Column('metadata', sa.JSON(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('global_access = 0 OR project_id IS NULL', name='ck_workers_single_scope'),
    sa.CheckConstraint('global_access IN (0, 1)', name='ck_workers_global_access_boolean'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workers_name', 'workers', ['name'], unique=True)
    op.create_index('ix_workers_project_id', 'workers', ['project_id'], unique=False)
    op.create_index('ix_workers_status', 'workers', ['status'], unique=False)
    op.create_table('agent_instances',
    sa.Column('workspace_id', sa.String(length=36), nullable=False),
    sa.Column('team_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('role_id', sa.String(length=100), nullable=False),
    sa.Column('module', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('capabilities', sa.JSON(), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
    sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('automation_commands',
    sa.Column('automation_id', sa.String(length=36), nullable=False),
    sa.Column('principal_id', sa.String(length=36), nullable=False),
    sa.Column('command', sa.String(length=30), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=False),
    sa.Column('request_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('postcondition', sa.JSON(), nullable=False),
    sa.Column('result_revision', sa.BigInteger(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("command IN ('update', 'enable', 'disable', 'webhook.disable')", name='ck_automation_commands_command'),
    sa.CheckConstraint('result_revision >= 1', name='ck_automation_commands_result_revision'),
    sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], ),
    sa.ForeignKeyConstraint(['principal_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('automation_id', 'principal_id', 'command', 'idempotency_key', name='uq_automation_command_principal_key')
    )
    op.create_index('ix_automation_commands_automation_id', 'automation_commands', ['automation_id'], unique=False)
    op.create_index('ix_automation_commands_principal_id', 'automation_commands', ['principal_id'], unique=False)
    op.create_table('automation_webhook_rotations',
    sa.Column('automation_id', sa.String(length=36), nullable=False),
    sa.Column('principal_id', sa.String(length=36), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=False),
    sa.Column('request_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('secret_hash', sa.String(length=64), nullable=False),
    sa.Column('rotation_number', sa.Integer(), nullable=False),
    sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('rotation_number >= 1', name='ck_webhook_rotation_number_positive'),
    sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], ),
    sa.ForeignKeyConstraint(['principal_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('automation_id', 'principal_id', 'idempotency_key', name='uq_webhook_rotation_principal_key'),
    sa.UniqueConstraint('automation_id', 'rotation_number', name='uq_webhook_rotation_number')
    )
    op.create_index('ix_automation_webhook_rotations_automation_id', 'automation_webhook_rotations', ['automation_id'], unique=False)
    op.create_index('ix_automation_webhook_rotations_principal_id', 'automation_webhook_rotations', ['principal_id'], unique=False)
    op.create_table('conversation_turns',
    sa.Column('conversation_id', sa.String(length=36), nullable=False),
    sa.Column('client_request_id', sa.String(length=128), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=False),
    sa.Column('user_content', sa.Text(), nullable=False),
    sa.Column('requested_model', sa.String(length=200), nullable=True),
    sa.Column('assistant_content', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('provider_run_id', sa.String(length=100), nullable=True),
    sa.Column('provider_model', sa.String(length=200), nullable=True),
    sa.Column('usage', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('conversation_id', 'client_request_id', name='uq_conversation_turn_client_request')
    )
    op.create_index('ix_conversation_turns_conversation_id', 'conversation_turns', ['conversation_id'], unique=False)
    op.create_index('ix_conversation_turns_idempotency_key', 'conversation_turns', ['idempotency_key'], unique=True)
    op.create_index('ix_conversation_turns_provider_run_id', 'conversation_turns', ['provider_run_id'], unique=True)
    op.create_index('ix_conversation_turns_status', 'conversation_turns', ['status'], unique=False)
    op.create_index('ix_conversation_turns_updated_at', 'conversation_turns', ['updated_at'], unique=False)
    op.create_table('mcp_servers',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('source_kind', sa.String(length=20), nullable=False),
    sa.Column('origin', sa.String(length=500), nullable=False),
    sa.Column('transport', sa.String(length=10), nullable=False),
    sa.Column('execution_location', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('current_revision_id', sa.String(length=36), nullable=True),
    sa.Column('target_worker_id', sa.String(length=36), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_reason', sa.Text(), nullable=False),
    sa.Column('last_probe_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['target_worker_id'], ['workers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mcp_servers_created_by_user_id', 'mcp_servers', ['created_by_user_id'], unique=False)
    op.create_index('ix_mcp_servers_name', 'mcp_servers', ['name'], unique=True)
    op.create_index('ix_mcp_servers_status', 'mcp_servers', ['status'], unique=False)
    op.create_table('scheduler_leases',
    sa.Column('scheduler_key', sa.String(length=64), nullable=False),
    sa.Column('owner_worker_id', sa.String(length=36), nullable=True),
    sa.Column('holder_id', sa.String(length=64), nullable=True),
    sa.Column('fencing_token', sa.Integer(), server_default='0', nullable=False),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_renewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('fencing_token >= 0', name='ck_scheduler_leases_fencing_token'),
    sa.ForeignKeyConstraint(['owner_worker_id'], ['workers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scheduler_key', name='uq_scheduler_leases_key')
    )
    op.create_index('ix_scheduler_leases_lease_expires_at', 'scheduler_leases', ['lease_expires_at'], unique=False)
    op.create_index('ix_scheduler_leases_owner_worker_id', 'scheduler_leases', ['owner_worker_id'], unique=False)
    op.create_table('mcp_server_revisions',
    sa.Column('server_id', sa.String(length=36), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('discovery', sa.JSON(), nullable=True),
    sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('discovery_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('risk_flags', sa.JSON(), nullable=False),
    sa.Column('change_summary', sa.JSON(), nullable=False),
    sa.Column('requires_approval', sa.Integer(), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['server_id'], ['mcp_servers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('server_id', 'number', name='uq_mcp_server_revision_number')
    )
    op.create_index('ix_mcp_server_revisions_fingerprint', 'mcp_server_revisions', ['fingerprint'], unique=False)
    op.create_index('ix_mcp_server_revisions_server_id', 'mcp_server_revisions', ['server_id'], unique=False)
    op.create_table('tasks',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('team_id', sa.String(length=36), nullable=True),
    sa.Column('agent_instance_id', sa.String(length=36), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('workflow_step', sa.String(length=100), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('meta', sa.JSON(), nullable=False),
    sa.Column('is_mission', sa.Integer(), nullable=False),
    sa.Column('objective', sa.Text(), nullable=False),
    sa.Column('expected_outcome', sa.Text(), nullable=False),
    sa.Column('acceptance_criteria', sa.JSON(), nullable=False),
    sa.Column('autonomy', sa.JSON(), nullable=False),
    sa.Column('resources', sa.JSON(), nullable=False),
    sa.Column('budget', sa.JSON(), nullable=False),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('attempt_counter', sa.Integer(), nullable=False),
    sa.Column('active_run_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    *_tasks_active_run_foreign_key(),
    sa.ForeignKeyConstraint(['agent_instance_id'], ['agent_instances.id'], ),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tasks_active_run_id', 'tasks', ['active_run_id'], unique=False)
    op.create_index('ix_tasks_created_by_user_id', 'tasks', ['created_by_user_id'], unique=False)
    op.create_index('ix_tasks_is_mission', 'tasks', ['is_mission'], unique=False)
    op.create_index('ix_tasks_status', 'tasks', ['status'], unique=False)
    op.create_table('team_members',
    sa.Column('team_id', sa.String(length=36), nullable=False),
    sa.Column('agent_instance_id', sa.String(length=36), nullable=False),
    sa.Column('role_id', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['agent_instance_id'], ['agent_instances.id'], ),
    sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
    sa.PrimaryKeyConstraint('team_id', 'agent_instance_id')
    )
    op.create_table('alerts',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=50), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('detail', sa.Text(), nullable=False),
    sa.Column('task_id', sa.String(length=36), nullable=True),
    sa.Column('automation_id', sa.String(length=36), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('acknowledged_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('acknowledgement_comment', sa.Text(), server_default='', nullable=False),
    sa.Column('dedupe_key', sa.String(length=64), nullable=False),
    sa.Column('dedupe_key_active', sa.String(length=64), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("severity IN ('info', 'warning', 'critical')", name='ck_alerts_severity'),
    sa.ForeignKeyConstraint(['acknowledged_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'dedupe_key_active', name='uq_alerts_dedupe_active')
    )
    op.create_index('ix_alerts_acknowledged_by_user_id', 'alerts', ['acknowledged_by_user_id'], unique=False)
    op.create_index('ix_alerts_kind', 'alerts', ['kind'], unique=False)
    op.create_index('ix_alerts_project_id', 'alerts', ['project_id'], unique=False)
    op.create_table('automation_runs',
    sa.Column('automation_id', sa.String(length=36), nullable=False),
    sa.Column('fire_key', sa.String(length=64), nullable=False),
    sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=False),
    sa.Column('fired_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('schedule_timezone', sa.String(length=64), server_default='Europe/Paris', nullable=False),
    sa.Column('task_id', sa.String(length=36), nullable=True),
    sa.Column('trigger_kind', sa.String(length=20), server_default='schedule', nullable=False),
    sa.Column('outcome', sa.String(length=30), nullable=False),
    sa.Column('detail', sa.String(length=500), nullable=False),
    sa.Column('completion_observed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completion_status', sa.String(length=30), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("outcome IN ('launched', 'skipped_concurrency', 'skipped_disabled', 'skipped_catchup', 'failed')", name='ck_automation_runs_outcome'),
    sa.CheckConstraint("trigger_kind IN ('manual', 'schedule', 'webhook')", name='ck_automation_runs_trigger_kind'),
    sa.CheckConstraint('length(schedule_timezone) > 0', name='ck_automation_runs_schedule_timezone_nonempty'),
    sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('automation_id', 'fire_key', name='uq_automation_runs_fire_key')
    )
    op.create_index('ix_automation_runs_automation_id', 'automation_runs', ['automation_id'], unique=False)
    op.create_index('ix_automation_runs_completion_observed_at', 'automation_runs', ['completion_observed_at'], unique=False)
    op.create_index('ix_automation_runs_reconcile_order', 'automation_runs', ['automation_id', 'completion_observed_at', 'scheduled_for', 'id', 'outcome'], unique=False)
    op.create_table('mcp_bindings',
    sa.Column('server_id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('revision_id', sa.String(length=36), nullable=False),
    sa.Column('allowed_tools', sa.JSON(), nullable=False),
    sa.Column('enabled', sa.Integer(), nullable=False),
    sa.Column('created_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['revision_id'], ['mcp_server_revisions.id'], ),
    sa.ForeignKeyConstraint(['server_id'], ['mcp_servers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('server_id', 'project_id', name='uq_mcp_binding_server_project')
    )
    op.create_index('ix_mcp_bindings_project_id', 'mcp_bindings', ['project_id'], unique=False)
    op.create_index('ix_mcp_bindings_server_id', 'mcp_bindings', ['server_id'], unique=False)
    op.create_table('mcp_probes',
    sa.Column('server_id', sa.String(length=36), nullable=False),
    sa.Column('revision_id', sa.String(length=36), nullable=False),
    sa.Column('transport', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('authorization', sa.JSON(), nullable=False),
    sa.Column('requested_by_user_id', sa.String(length=36), nullable=False),
    sa.Column('decided_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_comment', sa.Text(), nullable=False),
    sa.Column('worker_id', sa.String(length=36), nullable=True),
    sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['revision_id'], ['mcp_server_revisions.id'], ),
    sa.ForeignKeyConstraint(['server_id'], ['mcp_servers.id'], ),
    sa.ForeignKeyConstraint(['worker_id'], ['workers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mcp_probes_revision_id', 'mcp_probes', ['revision_id'], unique=False)
    op.create_index('ix_mcp_probes_server_id', 'mcp_probes', ['server_id'], unique=False)
    op.create_index('ix_mcp_probes_status', 'mcp_probes', ['status'], unique=False)
    op.create_index('ix_mcp_probes_worker_id', 'mcp_probes', ['worker_id'], unique=False)
    op.create_table('task_runs',
    sa.Column('task_id', sa.String(length=36), nullable=False),
    sa.Column('agent_instance_id', sa.String(length=36), nullable=True),
    sa.Column('session_id', sa.String(length=36), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('plan', sa.JSON(), nullable=True),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('logs', sa.JSON(), nullable=False),
    sa.Column('attempt_number', sa.Integer(), nullable=False),
    sa.Column('fencing_token', sa.Integer(), nullable=False),
    sa.Column('stop_requested_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('stop_requested_by_user_id', sa.String(length=36), nullable=True),
    sa.Column('technical_validation', sa.JSON(), nullable=False),
    sa.Column('user_acceptance', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['agent_instance_id'], ['agent_instances.id'], ),
    sa.ForeignKeyConstraint(['stop_requested_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_task_runs_attempt_number', 'task_runs', ['attempt_number'], unique=False)
    op.create_index('ix_task_runs_updated_at', 'task_runs', ['updated_at'], unique=False)
    if not _is_sqlite():
        op.create_foreign_key(None, 'tasks', 'task_runs', ['active_run_id'], ['id'])
    op.create_table('approvals',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('task_run_id', sa.String(length=36), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('target', sa.String(length=1000), nullable=False),
    sa.Column('consequences', sa.JSON(), nullable=False),
    sa.Column('scope', sa.JSON(), nullable=False),
    sa.Column('footprint', sa.JSON(), nullable=False),
    sa.Column('action_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('context', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('requested_by', sa.String(length=200), nullable=False),
    sa.Column('decided_by', sa.String(length=200), nullable=True),
    sa.Column('decision_comment', sa.Text(), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('invalidated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('invalidated_reason', sa.Text(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_approvals_action', 'approvals', ['action'], unique=False)
    op.create_index('ix_approvals_action_fingerprint', 'approvals', ['action_fingerprint'], unique=False)
    op.create_index('ix_approvals_project_id', 'approvals', ['project_id'], unique=False)
    op.create_index('ix_approvals_status', 'approvals', ['status'], unique=False)
    op.create_table('artifacts',
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('task_run_id', sa.String(length=36), nullable=False),
    sa.Column('worker_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=100), nullable=False),
    sa.Column('path', sa.String(length=1000), nullable=False),
    sa.Column('checksum', sa.String(length=200), nullable=True),
    sa.Column('size_bytes', sa.Integer(), nullable=True),
    sa.Column('metadata', sa.JSON(), nullable=False),
    sa.Column('storage_key', sa.String(length=200), nullable=True),
    sa.Column('content_type', sa.String(length=200), server_default='application/octet-stream', nullable=False),
    sa.Column('original_name', sa.String(length=500), server_default='', nullable=False),
    sa.Column('source', sa.String(length=50), server_default='worker', nullable=False),
    sa.Column('stream_kind', sa.String(length=50), server_default='', nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id'], ),
    sa.ForeignKeyConstraint(['worker_id'], ['workers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_artifacts_project_id', 'artifacts', ['project_id'], unique=False)
    op.create_index('ix_artifacts_storage_key', 'artifacts', ['storage_key'], unique=False)
    op.create_index('ix_artifacts_task_run_id', 'artifacts', ['task_run_id'], unique=False)
    op.create_index('ix_artifacts_worker_id', 'artifacts', ['worker_id'], unique=False)
    op.create_table('budget_usage',
    sa.Column('task_run_id', sa.String(length=36), nullable=False),
    sa.Column('cost', sa.Numeric(precision=18, scale=6), server_default='0', nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='EUR', nullable=False),
    sa.Column('tokens_input', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('tokens_output', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('tool_calls', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('usage_reported', sa.Integer(), server_default='0', nullable=False),
    sa.Column('cost_reported', sa.Integer(), server_default='0', nullable=False),
    sa.Column('tokens_input_reported', sa.Integer(), server_default='0', nullable=False),
    sa.Column('tokens_output_reported', sa.Integer(), server_default='0', nullable=False),
    sa.Column('tool_calls_reported', sa.Integer(), server_default='0', nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('cost >= 0 AND cost <= 999999999999', name='ck_budget_usage_cost_capacity'),
    sa.CheckConstraint('cost_reported IN (0, 1)', name='ck_budget_usage_cost_reported_boolean'),
    sa.CheckConstraint('tokens_input >= 0 AND tokens_input <= 9007199254740991', name='ck_budget_usage_tokens_input_capacity'),
    sa.CheckConstraint('tokens_input_reported IN (0, 1)', name='ck_budget_usage_tokens_input_reported_boolean'),
    sa.CheckConstraint('tokens_output >= 0 AND tokens_output <= 9007199254740991', name='ck_budget_usage_tokens_output_capacity'),
    sa.CheckConstraint('tokens_output_reported IN (0, 1)', name='ck_budget_usage_tokens_output_reported_boolean'),
    sa.CheckConstraint('tool_calls >= 0 AND tool_calls <= 9007199254740991', name='ck_budget_usage_tool_calls_capacity'),
    sa.CheckConstraint('tool_calls_reported IN (0, 1)', name='ck_budget_usage_tool_calls_reported_boolean'),
    sa.CheckConstraint('usage_reported IN (0, 1)', name='ck_budget_usage_usage_reported_boolean'),
    sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_budget_usage_task_run_id', 'budget_usage', ['task_run_id'], unique=True)
    op.create_table('budget_usage_reports',
    sa.Column('task_run_id', sa.String(length=36), nullable=False),
    sa.Column('report_id', sa.String(length=128), nullable=False),
    sa.Column('permit_id', sa.String(length=128), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('provider', sa.String(length=100), nullable=False),
    sa.Column('kind', sa.String(length=20), server_default='usage', nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('phase', sa.String(length=20), nullable=False),
    sa.Column('cost', sa.Numeric(precision=18, scale=6), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('tokens_input', sa.BigInteger(), nullable=True),
    sa.Column('tokens_output', sa.BigInteger(), nullable=True),
    sa.Column('tool_calls', sa.BigInteger(), nullable=True),
    sa.Column('estimated', sa.Integer(), server_default='0', nullable=False),
    sa.Column('allowed', sa.Integer(), server_default='1', nullable=False),
    sa.Column('accounting_day', sa.String(length=10), nullable=False),
    sa.Column('verdict_snapshot', sa.JSON(), nullable=False),
    sa.Column('reconciled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('reservation', 'usage')", name='ck_budget_report_kind'),
    sa.CheckConstraint("phase IN ('planning', 'execution', 'evaluation', 'tool')", name='ck_budget_report_phase'),
    sa.CheckConstraint("source IN ('provider', 'platform')", name='ck_budget_report_source'),
    sa.CheckConstraint('(cost IS NULL AND currency IS NULL) OR (cost IS NOT NULL AND currency IS NOT NULL)', name='ck_budget_report_cost_currency'),
    sa.CheckConstraint('allowed IN (0, 1)', name='ck_budget_report_allowed'),
    sa.CheckConstraint('cost IS NOT NULL OR tokens_input IS NOT NULL OR tokens_output IS NOT NULL OR tool_calls IS NOT NULL', name='ck_budget_report_has_measure'),
    sa.CheckConstraint('cost IS NULL OR (cost >= 0 AND cost <= 999999999999)', name='ck_budget_report_cost'),
    sa.CheckConstraint('estimated IN (0, 1)', name='ck_budget_report_estimated'),
    sa.CheckConstraint('length(accounting_day) = 10', name='ck_budget_report_accounting_day'),
    sa.CheckConstraint('tokens_input IS NULL OR tokens_input <= 9007199254740991', name='ck_budget_report_tokens_input_capacity'),
    sa.CheckConstraint('tokens_input IS NULL OR tokens_input >= 0', name='ck_budget_report_tokens_input'),
    sa.CheckConstraint('tokens_output IS NULL OR tokens_output <= 9007199254740991', name='ck_budget_report_tokens_output_capacity'),
    sa.CheckConstraint('tokens_output IS NULL OR tokens_output >= 0', name='ck_budget_report_tokens_output'),
    sa.CheckConstraint('tool_calls IS NULL OR tool_calls <= 9007199254740991', name='ck_budget_report_tool_calls_capacity'),
    sa.CheckConstraint('tool_calls IS NULL OR tool_calls >= 0', name='ck_budget_report_tool_calls'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_run_id', 'report_id', name='uq_budget_usage_reports_run_report')
    )
    op.create_index('ix_budget_usage_reports_accounting_day', 'budget_usage_reports', ['accounting_day'], unique=False)
    op.create_index('ix_budget_usage_reports_occurred_at', 'budget_usage_reports', ['occurred_at'], unique=False)
    op.create_index('ix_budget_usage_reports_project_id', 'budget_usage_reports', ['project_id'], unique=False)
    op.create_index('ix_budget_usage_reports_provider', 'budget_usage_reports', ['provider'], unique=False)
    op.create_index('ix_budget_usage_reports_task_run_id', 'budget_usage_reports', ['task_run_id'], unique=False)
    op.create_table('mission_commands',
    sa.Column('task_id', sa.String(length=36), nullable=False),
    sa.Column('command', sa.String(length=50), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=False),
    sa.Column('principal_id', sa.String(length=36), nullable=True),
    sa.Column('request_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('task_run_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['principal_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('principal_id', 'command', 'idempotency_key', name='uq_mission_command_principal_key')
    )
    op.create_index('ix_mission_commands_principal_id', 'mission_commands', ['principal_id'], unique=False)
    op.create_index('ix_mission_commands_task_id', 'mission_commands', ['task_id'], unique=False)
    op.create_table('mission_comments',
    sa.Column('task_id', sa.String(length=36), nullable=False),
    sa.Column('task_run_id', sa.String(length=36), nullable=True),
    sa.Column('author_user_id', sa.String(length=36), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=True),
    sa.Column('request_fingerprint', sa.String(length=64), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('idempotency_key IS NULL OR task_run_id IS NOT NULL', name='ck_mission_comment_key_requires_run'),
    sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('author_user_id', 'task_run_id', 'idempotency_key', name='uq_mission_comment_principal_run_key')
    )
    op.create_index('ix_mission_comments_author_user_id', 'mission_comments', ['author_user_id'], unique=False)
    op.create_index('ix_mission_comments_task_id', 'mission_comments', ['task_id'], unique=False)
    op.create_index('ix_mission_comments_task_run_id', 'mission_comments', ['task_run_id'], unique=False)
    op.create_table('mission_evidence',
    sa.Column('task_run_id', sa.String(length=36), nullable=False),
    sa.Column('worker_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=100), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('command', sa.Text(), nullable=True),
    sa.Column('exit_code', sa.Integer(), nullable=True),
    sa.Column('uri', sa.String(length=2000), nullable=True),
    sa.Column('checksum', sa.String(length=200), nullable=True),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id'], ),
    sa.ForeignKeyConstraint(['worker_id'], ['workers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_run_id', 'fingerprint', name='uq_mission_evidence_fingerprint')
    )
    op.create_index('ix_mission_evidence_task_run_id', 'mission_evidence', ['task_run_id'], unique=False)
    op.create_index('ix_mission_evidence_worker_id', 'mission_evidence', ['worker_id'], unique=False)
    op.create_table('resource_locks',
    sa.Column('resource_type', sa.String(length=50), nullable=False),
    sa.Column('resource_key', sa.String(length=1000), nullable=False),
    sa.Column('owner_run_id', sa.String(length=36), nullable=False),
    sa.Column('worker_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_renewed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_run_id'], ['task_runs.id'], ),
    sa.ForeignKeyConstraint(['worker_id'], ['workers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('resource_type', 'resource_key')
    )
    op.create_index('ix_resource_locks_owner_run_id', 'resource_locks', ['owner_run_id'], unique=False)
    op.create_index('ix_resource_locks_resource_type', 'resource_locks', ['resource_type'], unique=False)
    op.create_index('ix_resource_locks_status', 'resource_locks', ['status'], unique=False)
    op.create_index('ix_resource_locks_worker_id', 'resource_locks', ['worker_id'], unique=False)
    op.create_table('test_runs',
    sa.Column('task_run_id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('worker_id', sa.String(length=36), nullable=True),
    sa.Column('runner', sa.String(length=50), nullable=False),
    sa.Column('runner_version', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('totals', sa.JSON(), nullable=False),
    sa.Column('exit_code', sa.Integer(), nullable=True),
    sa.Column('report_artifact_id', sa.String(length=36), nullable=True),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id'], ),
    sa.ForeignKeyConstraint(['worker_id'], ['workers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_run_id', 'runner', name='uq_test_run_attempt_runner')
    )
    op.create_index('ix_test_runs_project_id', 'test_runs', ['project_id'], unique=False)
    op.create_index('ix_test_runs_status', 'test_runs', ['status'], unique=False)
    op.create_index('ix_test_runs_task_run_id', 'test_runs', ['task_run_id'], unique=False)
    op.create_table('worker_leases',
    sa.Column('worker_id', sa.String(length=36), nullable=False),
    sa.Column('task_id', sa.String(length=36), nullable=False),
    sa.Column('task_run_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=50), nullable=False),
    sa.Column('required_capabilities', sa.JSON(), nullable=False),
    sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_renewed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['task_run_id'], ['task_runs.id'], ),
    sa.ForeignKeyConstraint(['worker_id'], ['workers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_worker_leases_status', 'worker_leases', ['status'], unique=False)
    op.create_index('ix_worker_leases_task_id', 'worker_leases', ['task_id'], unique=False)
    op.create_index('ix_worker_leases_task_run_id', 'worker_leases', ['task_run_id'], unique=True)
    op.create_index('ix_worker_leases_worker_id', 'worker_leases', ['worker_id'], unique=False)
    op.create_table('artifact_links',
    sa.Column('artifact_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('used_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['artifact_id'], ['artifacts.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_artifact_links_artifact_id', 'artifact_links', ['artifact_id'], unique=False)
    op.create_index('ix_artifact_links_expires_at', 'artifact_links', ['expires_at'], unique=False)
    op.create_index('ix_artifact_links_token_hash', 'artifact_links', ['token_hash'], unique=True)
    op.create_index('ix_artifact_links_user_id', 'artifact_links', ['user_id'], unique=False)
    op.create_table('test_cases',
    sa.Column('test_run_id', sa.String(length=36), nullable=False),
    sa.Column('suite_path', sa.JSON(), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('test_id', sa.String(length=200), nullable=False),
    sa.Column('location', sa.JSON(), nullable=False),
    sa.Column('project_name', sa.String(length=200), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('expected_status', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('outcome', sa.String(length=20), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=False),
    sa.Column('error_snippet', sa.Text(), nullable=False),
    sa.Column('steps', sa.JSON(), nullable=False),
    sa.Column('annotations', sa.JSON(), nullable=False),
    sa.Column('attachment_artifact_ids', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['test_run_id'], ['test_runs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('test_run_id', 'test_id', 'attempt', name='uq_test_case_run_test_attempt')
    )
    op.create_index('ix_test_cases_outcome', 'test_cases', ['outcome'], unique=False)
    op.create_index('ix_test_cases_status', 'test_cases', ['status'], unique=False)
    op.create_index('ix_test_cases_test_run_id', 'test_cases', ['test_run_id'], unique=False)


def downgrade() -> None:
    """Retire les 47 tables dans l'ordre inverse de leur création.

    Sous PostgreSQL la clé circulaire est retirée avant ``task_runs``. Sous
    SQLite, seule une base sans lignes ``tasks.active_run_id`` renseignées peut
    redescendre : les clés étrangères y restent appliquées pendant le DROP.
    """
    op.drop_index('ix_test_cases_test_run_id', table_name='test_cases')
    op.drop_index('ix_test_cases_status', table_name='test_cases')
    op.drop_index('ix_test_cases_outcome', table_name='test_cases')
    op.drop_table('test_cases')
    op.drop_index('ix_artifact_links_user_id', table_name='artifact_links')
    op.drop_index('ix_artifact_links_token_hash', table_name='artifact_links')
    op.drop_index('ix_artifact_links_expires_at', table_name='artifact_links')
    op.drop_index('ix_artifact_links_artifact_id', table_name='artifact_links')
    op.drop_table('artifact_links')
    op.drop_index('ix_worker_leases_worker_id', table_name='worker_leases')
    op.drop_index('ix_worker_leases_task_run_id', table_name='worker_leases')
    op.drop_index('ix_worker_leases_task_id', table_name='worker_leases')
    op.drop_index('ix_worker_leases_status', table_name='worker_leases')
    op.drop_table('worker_leases')
    op.drop_index('ix_test_runs_task_run_id', table_name='test_runs')
    op.drop_index('ix_test_runs_status', table_name='test_runs')
    op.drop_index('ix_test_runs_project_id', table_name='test_runs')
    op.drop_table('test_runs')
    op.drop_index('ix_resource_locks_worker_id', table_name='resource_locks')
    op.drop_index('ix_resource_locks_status', table_name='resource_locks')
    op.drop_index('ix_resource_locks_resource_type', table_name='resource_locks')
    op.drop_index('ix_resource_locks_owner_run_id', table_name='resource_locks')
    op.drop_table('resource_locks')
    op.drop_index('ix_mission_evidence_worker_id', table_name='mission_evidence')
    op.drop_index('ix_mission_evidence_task_run_id', table_name='mission_evidence')
    op.drop_table('mission_evidence')
    op.drop_index('ix_mission_comments_task_run_id', table_name='mission_comments')
    op.drop_index('ix_mission_comments_task_id', table_name='mission_comments')
    op.drop_index('ix_mission_comments_author_user_id', table_name='mission_comments')
    op.drop_table('mission_comments')
    op.drop_index('ix_mission_commands_task_id', table_name='mission_commands')
    op.drop_index('ix_mission_commands_principal_id', table_name='mission_commands')
    op.drop_table('mission_commands')
    op.drop_index('ix_budget_usage_reports_task_run_id', table_name='budget_usage_reports')
    op.drop_index('ix_budget_usage_reports_provider', table_name='budget_usage_reports')
    op.drop_index('ix_budget_usage_reports_project_id', table_name='budget_usage_reports')
    op.drop_index('ix_budget_usage_reports_occurred_at', table_name='budget_usage_reports')
    op.drop_index('ix_budget_usage_reports_accounting_day', table_name='budget_usage_reports')
    op.drop_table('budget_usage_reports')
    op.drop_index('ix_budget_usage_task_run_id', table_name='budget_usage')
    op.drop_table('budget_usage')
    op.drop_index('ix_artifacts_worker_id', table_name='artifacts')
    op.drop_index('ix_artifacts_task_run_id', table_name='artifacts')
    op.drop_index('ix_artifacts_storage_key', table_name='artifacts')
    op.drop_index('ix_artifacts_project_id', table_name='artifacts')
    op.drop_table('artifacts')
    op.drop_index('ix_approvals_status', table_name='approvals')
    op.drop_index('ix_approvals_project_id', table_name='approvals')
    op.drop_index('ix_approvals_action_fingerprint', table_name='approvals')
    op.drop_index('ix_approvals_action', table_name='approvals')
    op.drop_table('approvals')
    if not _is_sqlite():
        op.drop_constraint('tasks_active_run_id_fkey', 'tasks', type_='foreignkey')
    op.drop_index('ix_task_runs_updated_at', table_name='task_runs')
    op.drop_index('ix_task_runs_attempt_number', table_name='task_runs')
    op.drop_table('task_runs')
    op.drop_index('ix_mcp_probes_worker_id', table_name='mcp_probes')
    op.drop_index('ix_mcp_probes_status', table_name='mcp_probes')
    op.drop_index('ix_mcp_probes_server_id', table_name='mcp_probes')
    op.drop_index('ix_mcp_probes_revision_id', table_name='mcp_probes')
    op.drop_table('mcp_probes')
    op.drop_index('ix_mcp_bindings_server_id', table_name='mcp_bindings')
    op.drop_index('ix_mcp_bindings_project_id', table_name='mcp_bindings')
    op.drop_table('mcp_bindings')
    op.drop_index('ix_automation_runs_reconcile_order', table_name='automation_runs')
    op.drop_index('ix_automation_runs_completion_observed_at', table_name='automation_runs')
    op.drop_index('ix_automation_runs_automation_id', table_name='automation_runs')
    op.drop_table('automation_runs')
    op.drop_index('ix_alerts_project_id', table_name='alerts')
    op.drop_index('ix_alerts_kind', table_name='alerts')
    op.drop_index('ix_alerts_acknowledged_by_user_id', table_name='alerts')
    op.drop_table('alerts')
    op.drop_table('team_members')
    op.drop_index('ix_tasks_status', table_name='tasks')
    op.drop_index('ix_tasks_is_mission', table_name='tasks')
    op.drop_index('ix_tasks_created_by_user_id', table_name='tasks')
    op.drop_index('ix_tasks_active_run_id', table_name='tasks')
    op.drop_table('tasks')
    op.drop_index('ix_mcp_server_revisions_server_id', table_name='mcp_server_revisions')
    op.drop_index('ix_mcp_server_revisions_fingerprint', table_name='mcp_server_revisions')
    op.drop_table('mcp_server_revisions')
    op.drop_index('ix_scheduler_leases_owner_worker_id', table_name='scheduler_leases')
    op.drop_index('ix_scheduler_leases_lease_expires_at', table_name='scheduler_leases')
    op.drop_table('scheduler_leases')
    op.drop_index('ix_mcp_servers_status', table_name='mcp_servers')
    op.drop_index('ix_mcp_servers_name', table_name='mcp_servers')
    op.drop_index('ix_mcp_servers_created_by_user_id', table_name='mcp_servers')
    op.drop_table('mcp_servers')
    op.drop_index('ix_conversation_turns_updated_at', table_name='conversation_turns')
    op.drop_index('ix_conversation_turns_status', table_name='conversation_turns')
    op.drop_index('ix_conversation_turns_provider_run_id', table_name='conversation_turns')
    op.drop_index('ix_conversation_turns_idempotency_key', table_name='conversation_turns')
    op.drop_index('ix_conversation_turns_conversation_id', table_name='conversation_turns')
    op.drop_table('conversation_turns')
    op.drop_index('ix_automation_webhook_rotations_principal_id', table_name='automation_webhook_rotations')
    op.drop_index('ix_automation_webhook_rotations_automation_id', table_name='automation_webhook_rotations')
    op.drop_table('automation_webhook_rotations')
    op.drop_index('ix_automation_commands_principal_id', table_name='automation_commands')
    op.drop_index('ix_automation_commands_automation_id', table_name='automation_commands')
    op.drop_table('automation_commands')
    op.drop_table('agent_instances')
    op.drop_index('ix_workers_status', table_name='workers')
    op.drop_index('ix_workers_project_id', table_name='workers')
    op.drop_index('ix_workers_name', table_name='workers')
    op.drop_table('workers')
    op.drop_table('teams')
    op.drop_index('ix_skill_bindings_skill_id', table_name='skill_bindings')
    op.drop_index('ix_skill_bindings_project_id', table_name='skill_bindings')
    op.drop_table('skill_bindings')
    op.drop_index('ix_secrets_revoked_at', table_name='secrets')
    op.drop_index('ix_secrets_project_id', table_name='secrets')
    op.drop_index('ix_secrets_name', table_name='secrets')
    op.drop_index('ix_secrets_created_by_user_id', table_name='secrets')
    op.drop_table('secrets')
    op.drop_index('ix_project_budget_policies_project_id', table_name='project_budget_policies')
    op.drop_table('project_budget_policies')
    op.drop_index('ix_notification_preferences_user_id', table_name='notification_preferences')
    op.drop_index('ix_notification_preferences_project_id', table_name='notification_preferences')
    op.drop_table('notification_preferences')
    op.drop_index('ix_conversations_updated_at', table_name='conversations')
    op.drop_index('ix_conversations_status', table_name='conversations')
    op.drop_index('ix_conversations_provider_session_id', table_name='conversations')
    op.drop_index('ix_conversations_project_id', table_name='conversations')
    op.drop_index('ix_conversations_created_by_user_id', table_name='conversations')
    op.drop_table('conversations')
    op.drop_index('ix_automations_project_id', table_name='automations')
    op.drop_index('ix_automations_next_run_at', table_name='automations')
    op.drop_index('ix_automations_created_by_user_id', table_name='automations')
    op.drop_table('automations')
    op.drop_table('projects')
    op.drop_index('ix_skill_revisions_skill_id', table_name='skill_revisions')
    op.drop_index('ix_skill_revisions_fingerprint', table_name='skill_revisions')
    op.drop_table('skill_revisions')
    op.drop_table('departments')
    op.drop_table('workspaces')
    op.drop_index('ix_user_sessions_user_id', table_name='user_sessions')
    op.drop_index('ix_user_sessions_token_hash', table_name='user_sessions')
    op.drop_index('ix_user_sessions_revoked_at', table_name='user_sessions')
    op.drop_index('ix_user_sessions_expires_at', table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_index('ix_skills_status', table_name='skills')
    op.drop_index('ix_skills_name', table_name='skills')
    op.drop_index('ix_skills_created_by_user_id', table_name='skills')
    op.drop_table('skills')
    op.drop_index('ix_users_platform_role', table_name='users')
    op.drop_index('ix_users_login_normalized', table_name='users')
    op.drop_table('users')
    op.drop_table('sessions')
    op.drop_table('providers')
    op.drop_table('organizations')
    op.drop_index('ix_memories_scope', table_name='memories')
    op.drop_index('ix_memories_owner_id', table_name='memories')
    op.drop_table('memories')
    op.drop_index('ix_memberships_user_id', table_name='memberships')
    op.drop_index('ix_memberships_scope_id', table_name='memberships')
    op.drop_table('memberships')
    op.drop_index('uq_events_journal_seq', table_name='events', sqlite_where=sa.text('journal_seq IS NOT NULL'), postgresql_where=sa.text('journal_seq IS NOT NULL'))
    op.drop_index('uq_event_run_sequence', table_name='events', sqlite_where=sa.text('task_run_id IS NOT NULL AND sequence IS NOT NULL'), postgresql_where=sa.text('task_run_id IS NOT NULL AND sequence IS NOT NULL'))
    op.drop_index('ix_events_type', table_name='events')
    op.drop_index('ix_events_task_run_sequence', table_name='events')
    op.drop_index('ix_events_project_id', table_name='events')
    op.drop_index('ix_events_journal_seq', table_name='events')
    op.drop_index('ix_events_conversation_id', table_name='events')
    op.drop_table('events')
