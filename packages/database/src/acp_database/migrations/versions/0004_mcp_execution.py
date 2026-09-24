"""Délégations MCP à durée limitée et réservations durables avant effets externes."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_execution_grants",
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("worker_id", sa.String(36), nullable=False),
        sa.Column("worker_token_hash", sa.String(64), nullable=False),
        sa.Column("task_run_id", sa.String(36), nullable=False),
        sa.Column("fencing_token", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.String(128), nullable=False),
        sa.Column("server_id", sa.String(36), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("allowed_tools", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"]),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["mcp_server_revisions.id"]),
    )
    op.create_index("ix_mcp_execution_grants_worker_id", "mcp_execution_grants", ["worker_id"])
    op.create_index("ix_mcp_execution_grants_task_run_id", "mcp_execution_grants", ["task_run_id"])
    op.create_table(
        "mcp_execution_calls",
        sa.Column("call_key", sa.String(64), nullable=False),
        sa.Column("task_run_id", sa.String(36), nullable=False),
        sa.Column("server_id", sa.String(36), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("step_id", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_key", name="uq_mcp_execution_call_key"),
        sa.CheckConstraint("status IN ('pending', 'succeeded', 'unknown', 'denied')",
                           name="ck_mcp_execution_call_status"),
        sa.ForeignKeyConstraint(["task_run_id"], ["task_runs.id"]),
        sa.ForeignKeyConstraint(["server_id"], ["mcp_servers.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["mcp_server_revisions.id"]),
    )
    op.create_index("ix_mcp_execution_calls_task_run_id", "mcp_execution_calls", ["task_run_id"])


def downgrade() -> None:
    connection = op.get_bind()
    # La preuve d'idempotence ne peut disparaître pendant qu'une tentative peut
    # encore reprendre ses outils. Le verrou précède la lecture de contrôle.
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE mcp_execution_calls IN ACCESS EXCLUSIVE MODE"))
    else:
        connection.execute(sa.text("UPDATE mcp_execution_calls SET status = status WHERE 1 = 0"))
    active = connection.execute(sa.text(
        "SELECT 1 FROM mcp_execution_calls c JOIN task_runs r ON r.id = c.task_run_id "
        "WHERE r.status IN ('pending', 'queued', 'preparing', 'running', 'waiting_approval', 'stopping') LIMIT 1"
    )).first()
    if active is not None:
        raise RuntimeError("Retour de schéma refusé : une tentative active conserve des appels MCP.")
    op.drop_index("ix_mcp_execution_calls_task_run_id", table_name="mcp_execution_calls")
    op.drop_table("mcp_execution_calls")
    op.drop_index("ix_mcp_execution_grants_task_run_id", table_name="mcp_execution_grants")
    op.drop_index("ix_mcp_execution_grants_worker_id", table_name="mcp_execution_grants")
    op.drop_table("mcp_execution_grants")
