"""add show_onboarding to users table

Revision ID: 2798464c1706
Revises: aff810fc119a
Create Date: 2026-04-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2798464c1706'
down_revision = 'aff810fc119a'
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.add_column('users', sa.Column('show_onboarding', sa.Boolean(), nullable=False, server_default='1'))


def downgrade() -> None:

    op.drop_column('users', 'show_onboarding')
