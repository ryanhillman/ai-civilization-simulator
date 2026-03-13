import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { agentApi, simApi, worldApi } from "@/api/client";
import type { AgentTurnSummary, TurnResult, World } from "@/types";
import { AgentAvatar } from "./AgentAvatar";

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

function VillageSummary({ agents, pressures }: {
  agents: AgentTurnSummary[];
  pressures: TurnResult["pressures"];
}) {
  const alive = agents.filter((a) => a.is_alive).length;
  const total = agents.length;
  const dead = total - alive;
  const sick = agents.filter((a) => a.is_alive && a.is_sick).length;
  const hungry = agents.filter((a) => a.is_alive && a.hunger >= 0.65).length;
  const avgPressure =
    pressures.length > 0
      ? pressures.reduce((s, p) => s + p.total, 0) / pressures.length
      : null;

  const pressureColor =
    avgPressure == null
      ? "text-stone-500"
      : avgPressure >= 2.5
      ? "text-red-400"
      : avgPressure >= 1.5
      ? "text-amber-400"
      : "text-green-400";

  return (
    <div className="px-4 py-2.5 border-b border-stone-800 text-xs space-y-1">
      <p className="text-stone-600 uppercase tracking-wider text-xs font-semibold mb-1.5">
        Village
      </p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <div className="flex items-center justify-between">
          <span className="text-stone-600">Population</span>
          <span className="text-stone-200 font-mono">{alive}/{total}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-stone-600">Dead</span>
          <span className={dead > 0 ? "text-stone-400 font-mono" : "text-stone-700 font-mono"}>
            {dead}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-stone-600">Sick</span>
          <span className={sick > 0 ? "text-red-400 font-mono" : "text-stone-700 font-mono"}>
            {sick}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-stone-600">Hungry</span>
          <span className={hungry > 0 ? "text-amber-400 font-mono" : "text-stone-700 font-mono"}>
            {hungry}
          </span>
        </div>
        {avgPressure !== null && (
          <div className="flex items-center justify-between col-span-2">
            <span className="text-stone-600">Avg pressure</span>
            <span className={`font-mono ${pressureColor}`}>{avgPressure.toFixed(2)}</span>
          </div>
        )}
      </div>
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

  type RosterAgent = {
    id: number;
    name: string;
    profession: string;
    hunger: number;
    is_alive: boolean;
    is_sick: boolean;
    pressureTotal: number | null;
  };

  const agentList: RosterAgent[] = lastResult
    ? lastResult.agents.map((a) => ({
        id: a.id,
        name: a.name,
        profession: a.profession,
        hunger: a.hunger,
        is_alive: a.is_alive,
        is_sick: a.is_sick,
        pressureTotal: a.pressure?.total ?? null,
      }))
    : (dbAgents ?? []).map((a) => ({
        ...a,
        pressureTotal: null,
      }));

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

      {/* Village summary — only when live data is available */}
      {lastResult && (
        <VillageSummary agents={lastResult.agents} pressures={lastResult.pressures} />
      )}

      {/* Agent roster */}
      <div className="panel-header">Villagers</div>
      <div className="overflow-y-auto flex-1">
        {agentList.map((agent) => (
          <button
            key={agent.id}
            className={`w-full text-left px-3 py-2.5 border-b border-stone-800/60 hover:bg-stone-800 transition-colors ${
              selectedAgentId === agent.id ? "bg-stone-800" : ""
            } ${!agent.is_alive ? "opacity-40" : ""}`}
            onClick={() => onSelectAgent(agent.id)}
          >
            <div className="flex items-center gap-2.5">
              <AgentAvatar
                id={agent.id}
                name={agent.name}
                isAlive={agent.is_alive}
                isSick={agent.is_sick && agent.is_alive}
                size={32}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-sm text-stone-200 font-medium truncate">
                    {agent.name}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0 ml-1">
                    {/* Pressure urgency dot */}
                    {agent.pressureTotal !== null && agent.pressureTotal >= 1.5 && (
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          agent.pressureTotal >= 2.5 ? "bg-red-400" : "bg-amber-400"
                        }`}
                        title={`Pressure: ${agent.pressureTotal.toFixed(2)}`}
                      />
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
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
