import axios from "axios";
import type {
  AgentDetail,
  AgentSummary,
  AskAgentRequest,
  AskAgentResponse,
  AutoplayRequest,
  EventDefinition,
  Memory,
  Relationship,
  RunNTurnsRequest,
  TriggerEventRequest,
  TurnEvent,
  TurnResult,
  World,
} from "@/types";

const http = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

// ---------------------------------------------------------------------------
// World
// ---------------------------------------------------------------------------

export const worldApi = {
  get: () => http.get<World>("/world").then((r) => r.data),

  create: (name: string) =>
    http.post<World>("/world", { name }).then((r) => r.data),

  reset: (worldId: number) =>
    http.delete<World>(`/world/${worldId}/reset`).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Simulation
// ---------------------------------------------------------------------------

export const simApi = {
  nextTurn: () =>
    http.post<TurnResult>("/simulation/turn").then((r) => r.data),

  runN: (body: RunNTurnsRequest) =>
    http.post<TurnResult[]>("/simulation/run", body).then((r) => r.data),

  autoplay: (body: AutoplayRequest) =>
    http.post<TurnResult[]>("/simulation/autoplay", body).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export const agentApi = {
  list: (worldId: number) =>
    http
      .get<AgentSummary[]>("/agents", { params: { world_id: worldId } })
      .then((r) => r.data),

  get: (agentId: number) =>
    http.get<AgentDetail>(`/agents/${agentId}`).then((r) => r.data),

  getMemories: (agentId: number) =>
    http.get<Memory[]>(`/agents/${agentId}/memories`).then((r) => r.data),

  getRelationships: (agentId: number) =>
    http
      .get<Relationship[]>(`/agents/${agentId}/relationships`)
      .then((r) => r.data),

  ask: (agentId: number, body: AskAgentRequest) =>
    http
      .post<AskAgentResponse>(`/agents/${agentId}/ask`, body)
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------

export const timelineApi = {
  list: (params: {
    world_id: number;
    turn?: number;
    agent_id?: number;
    event_type?: string;
  }) => http.get<TurnEvent[]>("/timeline", { params }).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

export const eventsApi = {
  listTriggerable: () =>
    http.get<EventDefinition[]>("/events/triggerable").then((r) => r.data),

  trigger: (body: TriggerEventRequest) =>
    http.post<TurnEvent>("/events/trigger", body).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------

export const systemApi = {
  health: () => http.get<{ status: string; env: string }>("/health").then((r) => r.data),
};
