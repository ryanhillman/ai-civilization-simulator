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
export type Visibility = "public" | "private";

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

export interface InventoryItem {
  resource_type: ResourceType;
  quantity: number;
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

export interface AgentDetail extends AgentSummary {
  personality_traits: PersonalityTraits;
  goals: Goal[];
  inventory: InventoryItem[];
  relationships: Relationship[];
  recent_memories: Memory[];
}

// ---------------------------------------------------------------------------
// Relationship
// ---------------------------------------------------------------------------

export interface Relationship {
  id: number;
  source_agent_id: number;
  target_agent_id: number;
  target_name?: string; // joined/resolved in response
  trust: number;
  warmth: number;
  respect: number;
  resentment: number;
  fear: number;
  alliance_active: boolean;
  grudge_active: boolean;
}

// ---------------------------------------------------------------------------
// Memory
// ---------------------------------------------------------------------------

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
  visibility: Visibility;
  created_at: string;
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
// Simulation
// ---------------------------------------------------------------------------

export interface TurnResult {
  world: World;
  events: TurnEvent[];
  turn_number: number;
}

export interface RunNTurnsRequest {
  turns: number;
}

export interface AutoplayRequest {
  max_turns: number;
}

// ---------------------------------------------------------------------------
// Ask-an-agent
// ---------------------------------------------------------------------------

export interface AskAgentRequest {
  question: string;
}

export interface AskAgentResponse {
  agent_id: number;
  agent_name: string;
  answer: string;
  turn_number: number;
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

export interface EventDefinition {
  type: EventType;
  label: string;
  description: string;
  params_schema: Record<string, unknown> | null;
}

export interface TriggerEventRequest {
  event_type: EventType;
  world_id: number;
  params?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// API response wrappers
// ---------------------------------------------------------------------------

export interface ApiError {
  detail: string;
}
