"""Migration script for pfs 2.

Revision ID: 0cef7bfd6333
Revises: d27bcad4dbf3
Create Date: 2025-02-10 11:00:12.033114

"""
import logging

import sqlalchemy as sa
import alembic

from lsst.daf.butler_migrate.butler_attributes import ButlerAttributes 

# revision identifiers, used by Alembic.
revision = "0cef7bfd6333"
down_revision = "d27bcad4dbf3"
branch_labels = None
depends_on = None

# Logger name should start with lsst to work with butler logging option.
_LOG = logging.getLogger(f"lsst.{__name__}")

# Lengths to set for string columns
# (table, column) -> length
_LENGTHS = {
    ("visit", "lamps"): 64,
    ("arm", "name"): 4,
    ("combination", "name"): 64,
    ("profiles_run", "run"): 64,
}

# Quantization to apply to dither values before converting to integer
_DITHER_QUANTIZE = 10000


def upgrade() -> None:
    """Upgrade from PFS version 1 to version 2.

    - Set 'length' for string columns:
        - visit.lamps
        - arm.name
        - combination.name
        - profiles_run.name
    - Convert dither.value and visit.dither from FLOAT to INT

    There is another change to dimensions.yaml, which is removing "detector"
    from topology.temporal.observation_timespans. I have no idea what that has
    to do with anything in the database, so I'm not changing anything about it
    here (except in the dimensions.yaml file stored in the butler_attributes).
    """
    _LOG.info("Upgrading to PFS version 2")

    # Set lengths for string columns
    for (table, column), length in _LENGTHS.items():
        _LOG.info("Setting length for %s.%s to %d", table, column, length)
        with alembic.op.batch_alter_table(table) as batch:
            batch.alter_column(column, type_=sa.String(length=length))

    # Convert dither.value and visit.dither from FLOAT to INT
    # We do this by creating a new "dither" table with the correct values,
    # converting the existing dither column in visit to the new integer values,
    # and then replacing the old dither table with the new one.
    # First, though, we have to remove the foreign key constraint linking
    # visit.dither to dither.value.
    alembic.op.drop_constraint("fkey_visit_dither_instrument_value_instrument_dither", "visit")

    # Create a new dither table with integer values
    _LOG.info("Converting dither.value to integer")
    alembic.op.create_table(
        "dither_temp",
        sa.Column("instrument", sa.String(16)),
        sa.Column("value", sa.Integer()),
    )
    conn = alembic.op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO dither_temp SELECT DISTINCT instrument, ROUND(value * :quantize) FROM dither"
        ),
        {"quantize": _DITHER_QUANTIZE},
    )
    alembic.op.drop_table("dither")
    alembic.op.rename_table("dither_temp", "dither")
    alembic.op.create_primary_key("dither_pkey", "dither", ["instrument", "value"])
    alembic.op.create_index("dither_fkidx_instrument", "dither", ["instrument"])
    alembic.op.create_foreign_key(
        "fkey_dither_instrument_name_instrument", "dither", "instrument", ["instrument"], ["name"]
    )

    # Convert visit.dither to integer
    _LOG.info("Converting visit.dither to integer")
    alembic.op.alter_column(
        "visit", "dither", type_=sa.Integer(), postgresql_using=f"(dither * {_DITHER_QUANTIZE})::integer"
    )

    # Recreate the foreign key constraint we deleted
    alembic.op.create_foreign_key(
        "fkey_visit_dither_instrument_value_instrument_dither",
        "visit",
        "dither",
        ("instrument", "dither"),
        ("instrument", "value"),
    )

    # Finally, we need to update the version of dimensions.yaml that's stored
    # in the database.
    _LOG.info("Converting butler attributes")
    schema = alembic.context.get_context().version_table_schema
    attributes = ButlerAttributes(conn, schema)

    def update_config(config):
        config["version"] = 2

        # Set lengths for string columns
        for (table, column), length in _LENGTHS.items():
            entry = None
            for name in ("keys", "metadata"):
                if name not in config["elements"][table]:
                    _LOG.debug("No entry for %s.%s in %s", table, column, name)
                    continue
                section = config["elements"][table][name]
                for item in section:
                    if item["name"] == column:
                        _LOG.debug("Found entry for %s.%s in %s", table, column, section)
                        assert entry is None, f"Found multiple entries for {table}.{column}"
                        entry = item
                        break
            assert entry is not None, f"Could not find entry for {table}.{column}"
            assert entry["type"] == "string", f"Expected {table}.{column} to be a string"
            entry["length"] = length

        # Convert dither to integer
        dither = config["elements"]["dither"]
        dither["doc"] = "A slit offset in the spatial dimension, quantized."
        ditherKeys = dither["keys"]
        assert len(ditherKeys) == 1, "Expected dither to have exactly one key"
        assert ditherKeys[0]["name"] == "value", "Expected dither to have a key named 'value'"
        ditherKeys[0]["type"] = "int"

        # Remove "detector" from topology.temporal.observation_timespans
        config["topology"]["temporal"]["observation_timespans"] = ["visit"]

        return config

    attributes.update_dimensions_json(update_config)


def downgrade() -> None:
    """Perform schema downgrade."""
    raise NotImplementedError("Downgrade left as an exercise for the reader")
