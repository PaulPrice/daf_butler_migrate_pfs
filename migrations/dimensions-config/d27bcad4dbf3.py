"""This is the base revision for PFS, version=1.

Revision ID: d27bcad4dbf3
Revises: 3e2891b82110
Create Date: 2025-02-10 06:11:02.882252

"""

# revision identifiers, used by Alembic.
revision = "d27bcad4dbf3"
down_revision = "3e2891b82110"
branch_labels = ("dimensions-config-pfs",)
depends_on = None

def upgrade() -> None:
    """Perform schema upgrade."""
    raise NotImplementedError("This revision is a base revision for PFS.")


def downgrade() -> None:
    """Perform schema downgrade."""
    raise NotImplementedError("Can't downgrade past base revision for PFS.")
