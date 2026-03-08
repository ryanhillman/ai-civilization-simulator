// ---------------------------------------------------------------------------
// Enums (mirror backend Python enums)
// ---------------------------------------------------------------------------

export type Season = "spring" | "summer" | "autumn" | "winter";
export type Profession =
  | "farmer"
  | "blacksmith"
  | "merchant"
  | "healer"
  | "priest"
  | "soldier";
export type ResourceType = "food" | "coin" | "wood" | "medicine";
export type EventType =
  | "trade"
  | "gossip"
  | "conflict"
  | "festival"
  | "sickness"
  | "weather"
  | "harvest"
  | "rest"
  | "theft";

// ---------------------------------------------------------------------------
// World
// ---------------------------------------------------------------------------

export interface World {
  id: number;
  name: string;
  current_turn: number;
  current_day: number;
  current_season: Season;
  weather: string;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Agent
// ---------------------------------------------------------------------------

export interface Inventory {
  food: number;
  coin: number;
  wood: number;
  medicine: number;
}

export interface PersonalityTraits {
  courage: number;
  greed: number;
  warmth: number;
  cunning: number;
  piety: number;
}

export interface Goal {
  type: string;
  target: string;
  priority: number;
}

export interface AgentSummary {
  id: number;
  name: string;
  profession: Profession;
  age: number;
  is_alive: boolean;
  is_sick: boolean;
  hunger: number;
}

export interface Relationship {
  id: number;
  source_agent_id: number;
  target_agent_id: number;
  target_name?: string;
  trust: number;
  warmth: number;
  respect: number;
  resentment: number;
  fear: number;
  alliance_active: boolean;
  grudge_active: boolean;
}

export interface Memory {
  id: number;
  agent_id: number;
  world_id: number;
  turn_number: number;
  event_type: EventType;
  summary: string;
  emotional_weight: number;
  related_agent_id: number | null;
  related_agent_name?: string;
  visibility: string;
  created_at: string;
}

export interface AgentDetail extends AgentSummary {
  personality_traits: PersonalityTraits;
  goals: Goal[];
  inventory: Inventory;
  relationships: Relationship[];
  recent_memories: Memory[];
}

// ---------------------------------------------------------------------------
// Simulation — pressure + turn result
// ---------------------------------------------------------------------------

export interface AgentPressure {
  agent_id: number;
  hunger_pressure: number;
  resource_pressure: number;
  sickness_pressure: number;
  social_pressure: number;
  memory_pressure: number;
  total: number;
  top_reasons: string[];
}

export interface ResolvedAction {
  agent_id: number;
  action_type: string;
  succeeded: boolean;
  outcome: string;
  details: Record<string, unknown>;
}

export interface TurnEventDomain {
  world_id: number;
  turn_number: number;
  event_type: string;
  description: string;
  agent_ids: number[];
  details: Record<string, unknown>;
}

export interface WorldEvent {
  event_type: string;
  description: string;
  affected_agent_ids: number[];
  modifiers: Record<string, unknown>;
}

export interface AgentTurnSummary extends AgentSummary {
  inventory: Inventory;
  pressure: AgentPressure | null;
}

export interface TurnResult {
  world_id: number;
  turn_number: number;
  current_day: number;
  current_season: Season;
  weather: string;
  agents: AgentTurnSummary[];
  resolved_actions: ResolvedAction[];
  events: TurnEventDomain[];
  world_events: WorldEvent[];
  pressures: AgentPressure[];
  summary: string;
}

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------

export interface TurnEvent {
  id: number;
  world_id: number;
  turn_number: number;
  event_type: EventType;
  description: string;
  narrative: string | null;
  agent_ids: number[];
  details: Record<string, unknown>;
  created_at: string;
}

// ---------------------------------------------------------------------------
// API response wrappers
// ---------------------------------------------------------------------------

export interface ApiError {
  detail: string;
}
