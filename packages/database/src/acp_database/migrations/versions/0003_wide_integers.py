"""Élargit les compteurs, tailles, durées et codes de sortie à 64 bits.

SQLite utilise déjà des INTEGER signés sur 64 bits : son DDL historique est
conservé, sans reconstruire des tables référencées par des clés étrangères.
Sous PostgreSQL, un downgrade contenant une valeur trop grande échoue et sa
transaction est annulée intégralement ; aucune valeur n'est tronquée.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

WIDE_COLUMNS = (
    ("artifacts", "size_bytes"),
    ("event_outbox", "journal_seq"),
    ("events", "journal_seq"),
    ("mission_evidence", "exit_code"),
    ("test_cases", "duration_ms"),
    ("test_runs", "duration_ms"),
    ("test_runs", "exit_code"),
)


REFERENCE_COLUMNS = (("mcp_servers", "origin"), ("skills", "origin"), ("skill_revisions", "source_ref"))

def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for table, column in REFERENCE_COLUMNS:
        op.alter_column(table, column, existing_type=sa.String(500), type_=sa.Text())
    for table, column in WIDE_COLUMNS:
        op.alter_column(table, column, existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for table, column in REFERENCE_COLUMNS:
        source = sa.table(table, sa.column(column, sa.Text()))
        too_long = op.get_bind().execute(
            sa.select(sa.func.count()).select_from(source).where(sa.func.length(source.c[column]) > 500)
        ).scalar_one()
        if too_long:
            raise RuntimeError("Retour arrière refusé : des références dépassent 500 caractères")
    for table, column in reversed(REFERENCE_COLUMNS):
        op.alter_column(table, column, existing_type=sa.Text(), type_=sa.String(500))
    for table, column in reversed(WIDE_COLUMNS):
        op.alter_column(table, column, existing_type=sa.BigInteger(), type_=sa.Integer())
