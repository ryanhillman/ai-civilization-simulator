import { useMutation, useQuery } from "@tanstack/react-query";
import { agentApi, aiApi } from "@/api/client";
import type { AgentPressure, AgentTurnSummary, AskAgentResponse, TurnResult } from "@/types";
import { useState } from "react";
import { AgentAvatar } from "./AgentAvatar";

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

// ---------------------------------------------------------------------------
// Ask-Agent section
// ---------------------------------------------------------------------------

function AskAgentSection({
  worldId,
  agentId,
  isAlive,
}: {
  worldId: number;
  agentId: number;
  isAlive: boolean;
}) {
  const [question, setQuestion] = useState("");
  const [lastAnswer, setLastAnswer] = useState<AskAgentResponse | null>(null);

  const ask = useMutation({
    mutationFn: () => aiApi.askAgent(worldId, agentId, question.trim()),
    onMutate: () => {
      setLastAnswer(null);   // clear stale answer the moment submit fires
    },
    onSuccess: (data) => {
      setLastAnswer(data);
      setQuestion("");
    },
  });

  const canSubmit = question.trim().length > 0 && !ask.isPending;

  if (!isAlive) {
    return (
      <div className="px-4 py-3 border-t border-stone-800">
        <p className="text-xs font-semibold text-stone-600 uppercase tracking-wider mb-2">
          Chronicle
        </p>
        <p className="text-xs text-stone-600 italic mb-3">
          This villager has passed away. Their story is recorded in the chronicle.
        </p>
        {lastAnswer?.agent_deceased && (
          <div className="mb-3 rounded bg-stone-900 border border-stone-700 px-3 py-2">
            <p className="text-xs text-stone-400 leading-relaxed">
              {lastAnswer.answer}
            </p>
            <p className="text-xs text-stone-700 mt-1">Historical record</p>
          </div>
        )}
        <div className="flex gap-2">
          <input
            className="flex-1 text-xs bg-stone-900 border border-stone-800 rounded px-2 py-1.5
                       text-stone-500 placeholder-stone-700 focus:outline-none focus:border-stone-700"
            placeholder="Ask about this villager..."
            value={question}
            maxLength={300}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSubmit) ask.mutate();
            }}
          />
          <button
            className="btn-secondary text-xs shrink-0 opacity-60"
            onClick={() => ask.mutate()}
            disabled={!canSubmit}
          >
            {ask.isPending ? "..." : "Recall"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-3 border-t border-stone-800">
      <p className="text-xs font-semibold text-stone-400 uppercase tracking-wider mb-2">
        Ask this villager
      </p>

      {lastAnswer && !lastAnswer.agent_deceased && (
        <div className="mb-3 rounded bg-stone-800/60 border border-stone-700 px-3 py-2">
          <p className="text-xs text-amber-200 leading-relaxed italic">
            &ldquo;{lastAnswer.answer}&rdquo;
          </p>
          {lastAnswer.fallback && (
            <p className="text-xs text-stone-600 mt-1">
              (AI unavailable — fallback response)
            </p>
          )}
        </div>
      )}

      {ask.isError && (
        <p className="text-xs text-red-400 mb-2">
          Could not reach the villager. Try again.
        </p>
      )}

      <div className="flex gap-2">
        <input
          className="flex-1 text-xs bg-stone-800 border border-stone-700 rounded px-2 py-1.5
                     text-stone-200 placeholder-stone-600 focus:outline-none focus:border-stone-500"
          placeholder="Ask a question..."
          value={question}
          maxLength={300}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && canSubmit) ask.mutate();
          }}
        />
        <button
          className="btn-secondary text-xs shrink-0"
          onClick={() => ask.mutate()}
          disabled={!canSubmit}
        >
          {ask.isPending ? "..." : "Ask"}
        </button>
      </div>
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
          <div className={`px-4 py-3 border-b border-stone-800 ${!agentDetail.is_alive ? "opacity-60" : ""}`}>
            <div className="flex items-center gap-3 mb-2.5">
              <div style={{ borderRadius: "50%", border: "2px solid rgba(255,255,255,0.1)", lineHeight: 0, flexShrink: 0 }}>
                <AgentAvatar
                  id={agentDetail.id}
                  name={agentDetail.name}
                  isAlive={agentDetail.is_alive}
                  isSick={agentDetail.is_sick && agentDetail.is_alive}
                  size={48}
                />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-1">
                  <h2 className="text-base font-semibold text-stone-100 truncate">
                    {agentDetail.name}
                  </h2>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    {agentDetail.is_sick && (
                      <span className="badge bg-red-900 text-red-300">sick</span>
                    )}
                    {!agentDetail.is_alive && (
                      <span className="badge bg-stone-800 text-stone-500">deceased</span>
                    )}
                  </div>
                </div>
                <p className="text-xs text-stone-500 capitalize">
                  {agentDetail.profession} · age {agentDetail.age}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
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
            <div className="px-4 py-3 border-b border-stone-800">
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

          {/* Ask this agent — AI interpretation */}
          <AskAgentSection worldId={worldId} agentId={agentDetail.id} isAlive={agentDetail.is_alive} />
        </div>
      ) : null}
    </div>
  );
}
