"""Boîte d'envoi transactionnelle des événements (``event_outbox``).

Révision : 0002
Précédente : 0001

Table neuve, définie aussi dans le modèle (``EventOutboxModel``) : sous SQLite,
``create_all`` la crée et ``init_db()`` estampille ; sous PostgreSQL seule cette
révision la crée. Le Lot H1 ne livre que le schéma ; le remplissage appartient au
Lot H3.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('event_outbox',
    sa.Column('event_id', sa.String(length=36), nullable=False),
    sa.Column('journal_seq', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('consumer', sa.String(length=50), server_default='event-service', nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dead_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.String(length=500), server_default='', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('attempts >= 0', name='ck_event_outbox_attempts_non_negative'),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
    sa.PrimaryKeyConstraint('event_id')
    )
    op.create_index('ix_event_outbox_journal_seq', 'event_outbox', ['journal_seq'], unique=False)
    op.create_index('ix_event_outbox_pending', 'event_outbox', ['consumer', 'next_attempt_at'], unique=False, sqlite_where=sa.text('delivered_at IS NULL AND dead_at IS NULL'), postgresql_where=sa.text('delivered_at IS NULL AND dead_at IS NULL'))


def downgrade() -> None:
    op.drop_index('ix_event_outbox_pending', table_name='event_outbox', sqlite_where=sa.text('delivered_at IS NULL AND dead_at IS NULL'), postgresql_where=sa.text('delivered_at IS NULL AND dead_at IS NULL'))
    op.drop_index('ix_event_outbox_journal_seq', table_name='event_outbox')
    op.drop_table('event_outbox')
