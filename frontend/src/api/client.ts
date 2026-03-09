import axios from "axios";
import type {
  AgentDetail,
  AgentSummary,
  AskAgentResponse,
  Memory,
  Relationship,
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
  list: () => http.get<World[]>("/worlds").then((r) => r.data),

  get: (worldId: number) =>
    http.get<World>(`/worlds/${worldId}`).then((r) => r.data),

  create: (name: string) =>
    http.post<World>("/worlds", { name }).then((r) => r.data),

  reset: (worldId: number) =>
    http.post<World>(`/worlds/${worldId}/reset`).then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Simulation
// ---------------------------------------------------------------------------

export const simApi = {
  nextTurn: (worldId: number) =>
    http.post<TurnResult>(`/worlds/${worldId}/turns/next`).then((r) => r.data),

  runN: (worldId: number, n: number) =>
    http.post<TurnResult[]>(`/worlds/${worldId}/turns/run`, { n }).then((r) => r.data),

  autoplay: (worldId: number, maxTurns: number) =>
    http
      .post<TurnResult[]>(`/worlds/${worldId}/turns/autoplay`, { max_turns: maxTurns })
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export const agentApi = {
  list: (worldId: number) =>
    http.get<AgentSummary[]>(`/worlds/${worldId}/agents`).then((r) => r.data),

  get: (worldId: number, agentId: number) =>
    http.get<AgentDetail>(`/worlds/${worldId}/agents/${agentId}`).then((r) => r.data),

  getMemories: (worldId: number, agentId: number) =>
    http
      .get<Memory[]>(`/worlds/${worldId}/agents/${agentId}/memories`)
      .then((r) => r.data),

  getRelationships: (worldId: number, agentId: number) =>
    http
      .get<Relationship[]>(`/worlds/${worldId}/agents/${agentId}/relationships`)
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------

export const timelineApi = {
  list: (
    worldId: number,
    params?: { turn?: number; agent_id?: number; event_type?: string; limit?: number }
  ) =>
    http
      .get<TurnEvent[]>(`/worlds/${worldId}/timeline`, { params })
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// AI
// ---------------------------------------------------------------------------

export const aiApi = {
  askAgent: (worldId: number, agentId: number, question: string) =>
    http
      .post<AskAgentResponse>(`/worlds/${worldId}/agents/${agentId}/ask`, {
        question,
      })
      .then((r) => r.data),
};

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------

export const systemApi = {
  health: () =>
    http.get<{ status: string; env: string }>("/health").then((r) => r.data),
};
