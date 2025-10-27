"""add current_activity to run table

Revision ID: b0e61a0fe5c2
Revises: 001_initial_schema
Create Date: 2025-10-26 00:32:03.135296

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "b0e61a0fe5c2"
down_revision: str | Sequence[str] | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
