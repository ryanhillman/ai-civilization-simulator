import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentApi, simApi, worldApi } from "@/api/client";
import type { TurnResult, World } from "@/types";

interface Props {
  worldId: number;
  world: World;
  lastResult: TurnResult | null;
  onSelectAgent: (agentId: number) => void;
  selectedAgentId: number | null;
  onResetWorld: () => void;
}

function HungerBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    value >= 0.7 ? "bg-red-500" : value >= 0.4 ? "bg-amber-500" : "bg-green-600";
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-16 bg-stone-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-stone-500">{pct}%</span>
    </div>
  );
}

export default function WorldPanel({
  worldId,
  world,
  lastResult,
  onSelectAgent,
  selectedAgentId,
  onResetWorld,
}: Props) {
  const qc = useQueryClient();

  // Use agent summaries from lastResult if available, else fetch
  const { data: dbAgents } = useQuery({
    queryKey: ["agents", worldId],
    queryFn: () => agentApi.list(worldId),
    enabled: lastResult === null,
  });

  const agentList: Array<{ id: number; name: string; profession: string; hunger: number; is_alive: boolean; is_sick: boolean }> =
    lastResult
      ? lastResult.agents.map((a) => ({
          id: a.id,
          name: a.name,
          profession: a.profession,
          hunger: a.hunger,
          is_alive: a.is_alive,
          is_sick: a.is_sick,
        }))
      : (dbAgents ?? []);

  const nextTurn = useMutation({
    mutationFn: () => simApi.nextTurn(worldId),
    onSuccess: (data) => {
      qc.setQueryData<TurnResult>(["lastResult", worldId], data);
      qc.invalidateQueries({ queryKey: ["world", worldId] });
      qc.invalidateQueries({ queryKey: ["timeline", worldId] });
    },
  });

  const run5 = useMutation({
    mutationFn: () => simApi.runN(worldId, 5),
    onSuccess: (data) => {
      if (data.length > 0) {
        qc.setQueryData<TurnResult>(["lastResult", worldId], data[data.length - 1]);
        qc.invalidateQueries({ queryKey: ["world", worldId] });
        qc.invalidateQueries({ queryKey: ["timeline", worldId] });
      }
    },
  });

  const autoplay = useMutation({
    mutationFn: () => simApi.autoplay(worldId, 20),
    onSuccess: (data) => {
      if (data.length > 0) {
        qc.setQueryData<TurnResult>(["lastResult", worldId], data[data.length - 1]);
        qc.invalidateQueries({ queryKey: ["world", worldId] });
        qc.invalidateQueries({ queryKey: ["timeline", worldId] });
      }
    },
  });

  const reset = useMutation({
    mutationFn: () => worldApi.reset(worldId),
    onSuccess: (resetWorld) => {
      qc.removeQueries({ queryKey: ["lastResult", worldId] });
      qc.setQueryData(["world", worldId], resetWorld);
      qc.invalidateQueries({ queryKey: ["worlds"] });
      qc.invalidateQueries({ queryKey: ["agents", worldId] });
      qc.invalidateQueries({ queryKey: ["timeline", worldId] });
      onResetWorld();
    },
  });

  const busy = nextTurn.isPending || run5.isPending || autoplay.isPending || reset.isPending;

  const displayWorld = lastResult
    ? {
        current_turn: lastResult.turn_number,
        calendar_date: lastResult.calendar_date,
        current_day: lastResult.current_day,
        current_season: lastResult.current_season,
        weather: lastResult.weather,
      }
    : world;

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">{world.name}</div>

      {/* World stats */}
      <div className="px-4 py-3 border-b border-stone-800 text-xs space-y-1.5">
        <div className="text-stone-200 font-medium">{displayWorld.calendar_date}</div>
        <div className="flex items-center justify-between">
          <span className="text-stone-500 capitalize">{displayWorld.weather}</span>
          <span className="text-stone-600 font-mono text-xs">turn {displayWorld.current_turn}</span>
        </div>
      </div>

      {/* Controls */}
      <div className="px-4 py-3 border-b border-stone-800 flex flex-wrap gap-2">
        <button
          className="btn-primary text-xs"
          onClick={() => nextTurn.mutate()}
          disabled={busy}
        >
          Next Turn
        </button>
        <button
          className="btn-secondary text-xs"
          onClick={() => run5.mutate()}
          disabled={busy}
        >
          Run 5
        </button>
        <button
          className="btn-secondary text-xs"
          onClick={() => autoplay.mutate()}
          disabled={busy}
        >
          Autoplay 20
        </button>
        <button
          className="btn-danger text-xs ml-auto"
          onClick={() => reset.mutate()}
          disabled={busy}
        >
          Reset
        </button>
      </div>

      {busy && (
        <div className="px-4 py-1 text-xs text-amber-400 border-b border-stone-800">
          Running...
        </div>
      )}

      {/* Agent roster */}
      <div className="panel-header">Villagers</div>
      <div className="overflow-y-auto flex-1">
        {agentList.map((agent) => (
          <button
            key={agent.id}
            className={`w-full text-left px-4 py-2.5 border-b border-stone-800/60 hover:bg-stone-800 transition-colors ${
              selectedAgentId === agent.id ? "bg-stone-800" : ""
            } ${!agent.is_alive ? "opacity-40" : ""}`}
            onClick={() => onSelectAgent(agent.id)}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm text-stone-200 font-medium">{agent.name}</span>
              <div className="flex gap-1">
                {agent.is_sick && (
                  <span className="badge bg-red-900 text-red-300">sick</span>
                )}
                {!agent.is_alive && (
                  <span className="badge bg-stone-800 text-stone-500">dead</span>
                )}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-stone-500 capitalize">{agent.profession}</span>
              <HungerBar value={agent.hunger} />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
