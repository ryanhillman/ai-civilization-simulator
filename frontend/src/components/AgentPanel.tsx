import { useQuery } from "@tanstack/react-query";
import { agentApi } from "@/api/client";
import type { AgentPressure, AgentTurnSummary, TurnResult } from "@/types";

interface Props {
  worldId: number;
  agentId: number | null;
  lastResult: TurnResult | null;
}

function StatBar({ label, value, color = "bg-amber-500" }: { label: string; value: number; color?: string }) {
  const pct = Math.min(100, Math.round(Math.abs(value) * 100));
  const isNeg = value < 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-stone-500 w-20 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-stone-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${isNeg ? "bg-red-600" : color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-stone-400 w-8 text-right font-mono">
        {value >= 0 ? "+" : ""}{value.toFixed(2)}
      </span>
    </div>
  );
}

function PressureSection({ pressure }: { pressure: AgentPressure }) {
  const total = pressure.total;
  const urgencyColor = total >= 2.5 ? "text-red-400" : total >= 1.5 ? "text-amber-400" : "text-green-400";
  return (
    <div className="px-4 py-3 border-b border-stone-800">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-stone-400 uppercase tracking-wider">Pressure</span>
        <span className={`text-sm font-mono font-bold ${urgencyColor}`}>
          {total.toFixed(2)}
          {total >= 2.5 && <span className="ml-1 text-xs">SURVIVAL</span>}
        </span>
      </div>
      <div className="space-y-1.5">
        <StatBar label="Hunger" value={pressure.hunger_pressure} color="bg-orange-500" />
        <StatBar label="Resource" value={pressure.resource_pressure} color="bg-amber-500" />
        <StatBar label="Sickness" value={pressure.sickness_pressure} color="bg-red-500" />
        <StatBar label="Social" value={pressure.social_pressure} color="bg-purple-500" />
        <StatBar label="Memory" value={pressure.memory_pressure} color="bg-blue-500" />
      </div>
      {pressure.top_reasons.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {pressure.top_reasons.map((r) => (
            <span key={r} className="badge bg-stone-800 text-stone-400 text-xs">{r}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AgentPanel({ worldId, agentId, lastResult }: Props) {
  const { data: agentDetail, isLoading } = useQuery({
    queryKey: ["agent", worldId, agentId],
    queryFn: () => agentApi.get(worldId, agentId!),
    enabled: agentId !== null,
  });

  if (agentId === null) {
    return (
      <div className="panel flex flex-col h-full overflow-hidden">
        <div className="panel-header">Agent Detail</div>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-stone-600 text-sm">Select a villager to inspect</p>
        </div>
      </div>
    );
  }

  // Pressure comes from lastResult (most recent turn)
  const liveSummary: AgentTurnSummary | undefined = lastResult?.agents.find(
    (a) => a.id === agentId
  );
  const pressure = liveSummary?.pressure ?? null;

  // Personality trait that matters most
  const traits = agentDetail?.personality_traits;

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">Agent Detail</div>

      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-stone-500 text-sm">Loading...</p>
        </div>
      ) : agentDetail ? (
        <div className="overflow-y-auto flex-1">
          {/* Header */}
          <div className="px-4 py-3 border-b border-stone-800">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-base font-semibold text-stone-100">{agentDetail.name}</h2>
                <p className="text-xs text-stone-500 capitalize">
                  {agentDetail.profession} · age {agentDetail.age}
                </p>
              </div>
              <div className="flex flex-col items-end gap-1">
                {agentDetail.is_sick && (
                  <span className="badge bg-red-900 text-red-300">sick</span>
                )}
                {!agentDetail.is_alive && (
                  <span className="badge bg-stone-800 text-stone-500">deceased</span>
                )}
              </div>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span className="text-xs text-stone-500">Hunger</span>
              <div className="flex-1 h-1.5 bg-stone-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    agentDetail.hunger >= 0.7 ? "bg-red-500" : agentDetail.hunger >= 0.4 ? "bg-amber-500" : "bg-green-600"
                  }`}
                  style={{ width: `${Math.round(agentDetail.hunger * 100)}%` }}
                />
              </div>
              <span className="text-xs text-stone-400 font-mono">
                {Math.round(agentDetail.hunger * 100)}%
              </span>
            </div>
          </div>

          {/* Pressure (live from last turn) */}
          {pressure && <PressureSection pressure={pressure} />}

          {/* Inventory */}
          <div className="px-4 py-3 border-b border-stone-800">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Inventory</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              {(["food", "coin", "wood", "medicine"] as const).map((r) => (
                <div key={r} className="flex justify-between">
                  <span className="text-stone-500 capitalize">{r}</span>
                  <span className="text-stone-200 font-mono">
                    {agentDetail.inventory[r].toFixed(1)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Traits */}
          {traits && (
            <div className="px-4 py-3 border-b border-stone-800">
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Traits</p>
              <div className="space-y-1.5">
                {Object.entries(traits).map(([k, v]) => (
                  <StatBar key={k} label={k} value={v} color="bg-stone-500" />
                ))}
              </div>
            </div>
          )}

          {/* Relationships */}
          {agentDetail.relationships.length > 0 && (
            <div className="px-4 py-3 border-b border-stone-800">
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">
                Relationships
              </p>
              <div className="space-y-2">
                {agentDetail.relationships.map((r) => (
                  <div key={r.id} className="text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-stone-300">{r.target_name ?? `Agent #${r.target_agent_id}`}</span>
                      <div className="flex gap-1">
                        {r.alliance_active && (
                          <span className="badge bg-emerald-900 text-emerald-300">ally</span>
                        )}
                        {r.grudge_active && (
                          <span className="badge bg-red-900 text-red-300">grudge</span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-3 text-stone-500">
                      <span>trust {r.trust >= 0 ? "+" : ""}{r.trust.toFixed(2)}</span>
                      <span>warmth {r.warmth >= 0 ? "+" : ""}{r.warmth.toFixed(2)}</span>
                      {r.resentment > 0 && (
                        <span className="text-red-400">resent {r.resentment.toFixed(2)}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Goals */}
          {agentDetail.goals.length > 0 && (
            <div className="px-4 py-3 border-b border-stone-800">
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">Goals</p>
              <div className="space-y-1">
                {agentDetail.goals.map((g, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="text-stone-600">#{g.priority}</span>
                    <span className="text-stone-400 capitalize">{g.type}</span>
                    <span className="text-stone-500">{g.target}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recent memories */}
          {agentDetail.recent_memories.length > 0 && (
            <div className="px-4 py-3">
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">
                Recent Memories
              </p>
              <div className="space-y-2">
                {agentDetail.recent_memories.slice(0, 10).map((m) => (
                  <div key={m.id} className="text-xs border-l-2 border-stone-700 pl-2">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="text-stone-600 font-mono">T{m.turn_number}</span>
                      <span
                        className={`uppercase font-mono ${
                          m.emotional_weight < -0.3
                            ? "text-red-400"
                            : m.emotional_weight > 0.3
                            ? "text-green-400"
                            : "text-stone-500"
                        }`}
                      >
                        {m.event_type}
                      </span>
                    </div>
                    <p className="text-stone-400">{m.summary}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
