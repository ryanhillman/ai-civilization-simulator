"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum types
    op.execute("CREATE TYPE season AS ENUM ('spring', 'summer', 'autumn', 'winter')")
    op.execute(
        "CREATE TYPE profession AS ENUM "
        "('farmer', 'blacksmith', 'merchant', 'healer', 'priest', 'soldier')"
    )
    op.execute(
        "CREATE TYPE resource_type AS ENUM ('food', 'coin', 'wood', 'medicine')"
    )
    op.execute(
        "CREATE TYPE event_type AS ENUM "
        "('trade', 'gossip', 'conflict', 'festival', 'sickness', "
        "'weather', 'harvest', 'rest', 'theft')"
    )
    op.execute("CREATE TYPE visibility AS ENUM ('public', 'private')")

    # worlds
    op.create_table(
        "worlds",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("current_turn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "current_season",
            PgEnum(name="season", create_type=False),
            nullable=False,
            server_default="spring",
        ),
        sa.Column("weather", sa.String(50), nullable=False, server_default="clear"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # agents
    op.create_table(
        "agents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "world_id",
            sa.BigInteger(),
            sa.ForeignKey("worlds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "profession",
            PgEnum(name="profession", create_type=False),
            nullable=False,
        ),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("is_alive", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_sick", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "hunger", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column("personality_traits", JSONB(), nullable=False, server_default="{}"),
        sa.Column("goals", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_agents_world_id", "agents", ["world_id"])

    # agent_inventory
    op.create_table(
        "agent_inventory",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "agent_id",
            sa.BigInteger(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_type",
            PgEnum(name="resource_type", create_type=False),
            nullable=False,
        ),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0.0"),
    )
    op.create_index("ix_inventory_agent_id", "agent_inventory", ["agent_id"])

    # relationships
    op.create_table(
        "relationships",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_agent_id",
            sa.BigInteger(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_agent_id",
            sa.BigInteger(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trust", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("warmth", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("respect", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("resentment", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("fear", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "alliance_active", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "grudge_active", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.create_index(
        "ix_relationships_source", "relationships", ["source_agent_id"]
    )
    op.create_index(
        "ix_relationships_pair",
        "relationships",
        ["source_agent_id", "target_agent_id"],
        unique=True,
    )

    # agent_memories
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "agent_id",
            sa.BigInteger(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "world_id",
            sa.BigInteger(),
            sa.ForeignKey("worlds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("event_type", PgEnum(name="event_type", create_type=False), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "emotional_weight", sa.Float(), nullable=False, server_default="0.0"
        ),
        sa.Column(
            "related_agent_id",
            sa.BigInteger(),
            sa.ForeignKey("agents.id"),
            nullable=True,
        ),
        sa.Column(
            "visibility",
            PgEnum(name="visibility", create_type=False),
            nullable=False,
            server_default="private",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_memories_agent_id", "agent_memories", ["agent_id"])
    op.create_index("ix_memories_world_turn", "agent_memories", ["world_id", "turn_number"])

    # turn_events
    op.create_table(
        "turn_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "world_id",
            sa.BigInteger(),
            sa.ForeignKey("worlds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("event_type", PgEnum(name="event_type", create_type=False), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("agent_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("details", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_turn_events_world_turn", "turn_events", ["world_id", "turn_number"])

    # rumors
    op.create_table(
        "rumors",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "world_id",
            sa.BigInteger(),
            sa.ForeignKey("worlds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_agent_id",
            sa.BigInteger(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_agent_id",
            sa.BigInteger(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("credibility", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("spread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("turn_created", sa.Integer(), nullable=False),
        sa.Column("turn_expires", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # rumor_knowledge
    op.create_table(
        "rumor_knowledge",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "agent_id",
            sa.BigInteger(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rumor_id",
            sa.BigInteger(),
            sa.ForeignKey("rumors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_learned", sa.Integer(), nullable=False),
        sa.Column("believed", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_table("rumor_knowledge")
    op.drop_table("rumors")
    op.drop_table("turn_events")
    op.drop_table("agent_memories")
    op.drop_table("relationships")
    op.drop_table("agent_inventory")
    op.drop_table("agents")
    op.drop_table("worlds")

    op.execute("DROP TYPE IF EXISTS visibility")
    op.execute("DROP TYPE IF EXISTS event_type")
    op.execute("DROP TYPE IF EXISTS resource_type")
    op.execute("DROP TYPE IF EXISTS profession")
    op.execute("DROP TYPE IF EXISTS season")
