"""rag: documents, chunks, index_meta, retrievals, citation_events, messages.grounding

Milestone 2 (FAP §14). Additive only: new tables and one nullable column, so the M1 image
still runs on this schema and a backend rollback needs no downgrade.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    embedding_type = Vector(384) if postgres else sa.JSON()

    op.create_table('documents',
    sa.Column('document_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('publisher', sa.Text(), nullable=False),
    sa.Column('publisher_short', sa.String(length=64), nullable=False),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('aliases', sa.JSON(), nullable=False),
    sa.Column('publisher_aliases', sa.JSON(), nullable=False),
    sa.Column('verified_by', sa.String(length=128), nullable=False),
    sa.Column('verified_on', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('document_id')
    )
    op.create_table('index_meta',
    sa.Column('corpus_version', sa.String(length=32), nullable=False),
    sa.Column('embedding_model', sa.String(length=128), nullable=False),
    sa.Column('dims', sa.Integer(), nullable=False),
    sa.Column('chunker_settings', sa.JSON(), nullable=False),
    sa.Column('chunk_count', sa.Integer(), nullable=False),
    sa.Column('built_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('corpus_version')
    )
    op.create_table('chunks',
    sa.Column('chunk_id', sa.String(length=128), nullable=False),
    sa.Column('document_id', sa.String(length=64), nullable=False),
    sa.Column('section_path', sa.JSON(), nullable=False),
    sa.Column('section', sa.Text(), nullable=False),
    sa.Column('page_start', sa.Integer(), nullable=True),
    sa.Column('page_end', sa.Integer(), nullable=True),
    sa.Column('ordinals', sa.JSON(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('embed_text', sa.Text(), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('restricted_category', sa.String(length=32), nullable=True),
    sa.Column('restricted_rule_id', sa.String(length=32), nullable=True),
    sa.Column('embedding', embedding_type, nullable=False),
    sa.Column('corpus_version', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.document_id'], ),
    sa.PrimaryKeyConstraint('chunk_id')
    )
    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.create_index('ix_chunks_document', ['document_id'], unique=False)

    op.create_table('retrievals',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('message_id', sa.Uuid(), nullable=True),
    sa.Column('failure_id', sa.Uuid(), nullable=True),
    sa.Column('query', sa.Text(), nullable=False),
    sa.Column('filter_document_id', sa.String(length=64), nullable=True),
    sa.Column('k', sa.Integer(), nullable=False),
    sa.Column('results', sa.JSON(), nullable=False),
    sa.Column('withheld', sa.JSON(), nullable=True),
    sa.Column('top_score', sa.Float(), nullable=True),
    sa.Column('corpus_version', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('(message_id IS NULL) <> (failure_id IS NULL)', name='ck_retrievals_one_owner'),
    sa.ForeignKeyConstraint(['failure_id'], ['failures.id'], ),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('citation_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('message_id', sa.Uuid(), nullable=True),
    sa.Column('failure_id', sa.Uuid(), nullable=True),
    sa.Column('claim_text', sa.Text(), nullable=False),
    sa.Column('source_label', sa.String(length=16), nullable=False),
    sa.Column('chunk_id', sa.String(length=128), nullable=True),
    sa.Column('reason', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['failure_id'], ['failures.id'], ),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('grounding', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('grounding')
    op.drop_table('citation_events')
    op.drop_table('retrievals')
    with op.batch_alter_table('chunks', schema=None) as batch_op:
        batch_op.drop_index('ix_chunks_document')
    op.drop_table('chunks')
    op.drop_table('index_meta')
    op.drop_table('documents')
    # The `vector` extension is left installed: other databases objects may use it.
