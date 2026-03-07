import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Season(str, enum.Enum):
    spring = "spring"
    summer = "summer"
    autumn = "autumn"
    winter = "winter"


class Profession(str, enum.Enum):
    farmer = "farmer"
    blacksmith = "blacksmith"
    merchant = "merchant"
    healer = "healer"
    priest = "priest"
    soldier = "soldier"


class ResourceType(str, enum.Enum):
    food = "food"
    coin = "coin"
    wood = "wood"
    medicine = "medicine"


class EventType(str, enum.Enum):
    trade = "trade"
    gossip = "gossip"
    conflict = "conflict"
    festival = "festival"
    sickness = "sickness"
    weather = "weather"
    harvest = "harvest"
    rest = "rest"
    theft = "theft"


class Visibility(str, enum.Enum):
    public = "public"
    private = "private"


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------


class World(Base):
    __tablename__ = "worlds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    current_turn: Mapped[int] = mapped_column(Integer, default=0)
    current_day: Mapped[int] = mapped_column(Integer, default=1)
    current_season: Mapped[Season] = mapped_column(
        Enum(Season, name="season"), default=Season.spring
    )
    weather: Mapped[str] = mapped_column(String(50), default="clear")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    agents: Mapped[list["Agent"]] = relationship(back_populates="world")
    turn_events: Mapped[list["TurnEvent"]] = relationship(back_populates="world")


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    world_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("worlds.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    profession: Mapped[Profession] = mapped_column(Enum(Profession, name="profession"))
    age: Mapped[int] = mapped_column(Integer)
    is_alive: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sick: Mapped[bool] = mapped_column(Boolean, default=False)
    # 0.0 = full, 1.0 = starving
    hunger: Mapped[float] = mapped_column(Float, default=0.0)
    # { courage, greed, warmth, cunning, piety } — each 0.0..1.0
    personality_traits: Mapped[dict] = mapped_column(JSONB, default=dict)
    # [{ type, target, priority }]
    goals: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    world: Mapped["World"] = relationship(back_populates="agents")
    inventory: Mapped[list["AgentInventory"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    memories: Mapped[list["AgentMemory"]] = relationship(
        foreign_keys="AgentMemory.agent_id",
        back_populates="agent",
        cascade="all, delete-orphan",
    )
    outgoing_relationships: Mapped[list["Relationship"]] = relationship(
        foreign_keys="Relationship.source_agent_id",
        back_populates="source_agent",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[list["Relationship"]] = relationship(
        foreign_keys="Relationship.target_agent_id",
        back_populates="target_agent",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# AgentInventory
# ---------------------------------------------------------------------------


class AgentInventory(Base):
    __tablename__ = "agent_inventory"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE")
    )
    resource_type: Mapped[ResourceType] = mapped_column(
        Enum(ResourceType, name="resource_type")
    )
    quantity: Mapped[float] = mapped_column(Float, default=0.0)

    agent: Mapped["Agent"] = relationship(back_populates="inventory")


# ---------------------------------------------------------------------------
# Relationship (directed: source -> target)
# ---------------------------------------------------------------------------


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE")
    )
    target_agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE")
    )
    # All dimensions: -1.0 (negative extreme) to 1.0 (positive extreme)
    trust: Mapped[float] = mapped_column(Float, default=0.0)
    warmth: Mapped[float] = mapped_column(Float, default=0.0)
    respect: Mapped[float] = mapped_column(Float, default=0.0)
    resentment: Mapped[float] = mapped_column(Float, default=0.0)
    fear: Mapped[float] = mapped_column(Float, default=0.0)
    # Derived from threshold scores — updated by social engine each turn
    alliance_active: Mapped[bool] = mapped_column(Boolean, default=False)
    grudge_active: Mapped[bool] = mapped_column(Boolean, default=False)

    source_agent: Mapped["Agent"] = relationship(
        foreign_keys=[source_agent_id], back_populates="outgoing_relationships"
    )
    target_agent: Mapped["Agent"] = relationship(
        foreign_keys=[target_agent_id], back_populates="incoming_relationships"
    )


# ---------------------------------------------------------------------------
# AgentMemory
# ---------------------------------------------------------------------------


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE")
    )
    world_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("worlds.id", ondelete="CASCADE")
    )
    turn_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType, name="event_type"))
    summary: Mapped[str] = mapped_column(Text)
    # -1.0 (traumatic) to 1.0 (joyful)
    emotional_weight: Mapped[float] = mapped_column(Float, default=0.0)
    related_agent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("agents.id"), nullable=True
    )
    visibility: Mapped[Visibility] = mapped_column(
        Enum(Visibility, name="visibility"), default=Visibility.private
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agent: Mapped["Agent"] = relationship(
        foreign_keys=[agent_id], back_populates="memories"
    )


# ---------------------------------------------------------------------------
# TurnEvent (canonical timeline entry)
# ---------------------------------------------------------------------------


class TurnEvent(Base):
    __tablename__ = "turn_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    world_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("worlds.id", ondelete="CASCADE")
    )
    turn_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType, name="event_type"))
    description: Mapped[str] = mapped_column(Text)
    # AI-generated narrative (optional, added after LLM call)
    narrative: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # IDs of agents involved
    agent_ids: Mapped[list] = mapped_column(JSONB, default=list)
    # Event-specific details (amounts, resource types, etc.)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    world: Mapped["World"] = relationship(back_populates="turn_events")


# ---------------------------------------------------------------------------
# Rumor + RumorKnowledge
# ---------------------------------------------------------------------------


class Rumor(Base):
    __tablename__ = "rumors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    world_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("worlds.id", ondelete="CASCADE")
    )
    source_agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE")
    )
    subject_agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE")
    )
    content: Mapped[str] = mapped_column(Text)
    # 0.0..1.0 — how believable this rumor is
    credibility: Mapped[float] = mapped_column(Float, default=0.5)
    spread_count: Mapped[int] = mapped_column(Integer, default=0)
    turn_created: Mapped[int] = mapped_column(Integer)
    turn_expires: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RumorKnowledge(Base):
    __tablename__ = "rumor_knowledge"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agents.id", ondelete="CASCADE")
    )
    rumor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rumors.id", ondelete="CASCADE")
    )
    turn_learned: Mapped[int] = mapped_column(Integer)
    believed: Mapped[bool] = mapped_column(Boolean, default=True)
