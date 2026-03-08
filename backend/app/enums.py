"""
Shared domain enumerations.

These enums represent core domain vocabulary used by both:
  - the simulation engine   (app.simulation)
  - the database layer      (app.models.db)

Keeping them here means importing app.simulation.types (or any simulation
stage) does NOT trigger loading of SQLAlchemy ORM machinery.

Boundary rule
-------------
  app.simulation.*  →  may import from app.enums          ✓
  app.simulation.*  →  must NOT import from app.models.db  ✗
  app.models.db     →  imports from app.enums              ✓
  app.domain.*      →  may import from both                ✓
"""
import enum


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
