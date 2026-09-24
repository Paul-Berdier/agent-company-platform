"""Derniers relevés des quotas réels d'abonnement (Codex, Claude Code) par worker.

Révision : 0005
Précédente : 0004

Table neuve, définie aussi dans le modèle (``SubscriptionQuotaSnapshotModel``) :
sous SQLite, ``create_all`` la crée et ``init_db()`` estampille ; sous PostgreSQL
seule cette révision la crée. Ces lignes sont un cache du dernier état lu à la
source par un worker, recréé au passage suivant : la descente les supprime sans
garde-fou de données.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_quota_snapshots",
        sa.Column("worker_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("limit_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("plan", sa.String(40), nullable=True),
        sa.Column("windows", sa.JSON(), nullable=False),
        sa.Column("credits", sa.JSON(), nullable=True),
        sa.Column("limit_reached", sa.Integer(), nullable=True),
        sa.Column("reached_type", sa.String(64), nullable=True),
        sa.Column("detail", sa.String(300), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "worker_id", "provider", "limit_id", name="uq_subscription_quota_snapshot"
        ),
        sa.CheckConstraint(
            "provider IN ('codex', 'claude_code')", name="ck_subscription_quota_provider"
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'not_signed_in', 'cli_missing', 'cli_too_old', 'unavailable')",
            name="ck_subscription_quota_status",
        ),
        sa.CheckConstraint(
            "source IN ('codex_app_server', 'claude_code_statusline')",
            name="ck_subscription_quota_source",
        ),
        sa.CheckConstraint(
            "limit_reached IS NULL OR limit_reached IN (0, 1)",
            name="ck_subscription_quota_limit_reached",
        ),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("subscription_quota_snapshots")
