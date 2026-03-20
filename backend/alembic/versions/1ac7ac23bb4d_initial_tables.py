"""Initial tables

Revision ID: 1ac7ac23bb4d
Revises:
Create Date: 2026-03-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1ac7ac23bb4d'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fmu_library',
        sa.Column('type_name', sa.String(length=100), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('fmu_path', sa.String(length=500), nullable=False),
        sa.Column('manifest', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('type_name'),
    )

    op.create_table(
        'projects',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('topology', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('ssp_path', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'simulation_jobs',
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('topology_hash', sa.String(length=64), nullable=True),
        sa.Column('ssp_path', sa.String(length=500), nullable=True),
        sa.Column('result_path', sa.String(length=500), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
        comment='Tracks composition and simulation jobs',
    )


def downgrade() -> None:
    op.drop_table('simulation_jobs')
    op.drop_table('projects')
    op.drop_table('fmu_library')
