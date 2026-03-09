import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { worldApi } from "@/api/client";
import type { TurnResult, World } from "@/types";
import AgentPanel from "@/components/AgentPanel";
import TimelinePanel from "@/components/TimelinePanel";
import WorldPanel from "@/components/WorldPanel";

// ---------------------------------------------------------------------------
// World selector / creator
// ---------------------------------------------------------------------------

function WorldSelector({ onSelect }: { onSelect: (w: World) => void }) {
  const qc = useQueryClient();
  const { data: worlds, isLoading } = useQuery({
    queryKey: ["worlds"],
    queryFn: worldApi.list,
  });

  const create = useMutation({
    mutationFn: () => worldApi.create("Ashenvale"),
    onSuccess: (w) => {
      qc.invalidateQueries({ queryKey: ["worlds"] });
      onSelect(w);
    },
  });

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-parchment-300 tracking-tight">
          AI Civilization Simulator
        </h1>
        <p className="mt-2 text-stone-400 text-sm">
          Medieval village · Turn-based · Autonomous agents
        </p>
      </div>

      <div className="panel px-6 py-5 w-80">
        <p className="text-sm font-semibold text-stone-300 mb-3">Select World</p>
        {isLoading ? (
          <p className="text-xs text-stone-500">Loading worlds...</p>
        ) : worlds && worlds.length > 0 ? (
          <div className="space-y-2">
            {worlds.map((w) => (
              <button
                key={w.id}
                className="w-full text-left px-3 py-2 rounded bg-stone-800 hover:bg-stone-700 transition-colors"
                onClick={() => onSelect(w)}
              >
                <div className="text-sm text-stone-200">{w.name}</div>
                <div className="text-xs text-stone-500">
                  {w.calendar_date}
                </div>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-stone-500 mb-3">No worlds yet.</p>
        )}

        <button
          className="btn-primary w-full mt-3 text-sm"
          onClick={() => create.mutate()}
          disabled={create.isPending}
        >
          {create.isPending ? "Creating..." : "New World (Ashenvale)"}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main dashboard
// ---------------------------------------------------------------------------

function Dashboard({ world, onBack }: { world: World; onBack: () => void }) {
  const qc = useQueryClient();
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);

  // Live world data (refreshed after turns)
  const { data: liveWorld } = useQuery({
    queryKey: ["world", world.id],
    queryFn: () => worldApi.get(world.id),
    initialData: world,
  });

  // Last turn result drives timeline and agent summaries
  const lastResult = qc.getQueryData<TurnResult>(["lastResult", world.id]) ?? null;

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Top bar */}
      <header className="shrink-0 border-b border-stone-800 px-4 py-2 flex items-center gap-4 bg-stone-950">
        <button
          className="btn-secondary text-xs"
          onClick={onBack}
        >
          Worlds
        </button>
        <h1 className="text-sm font-semibold text-stone-300">
          {liveWorld?.name ?? world.name}
        </h1>
        <span className="text-xs text-stone-600">
          {liveWorld?.calendar_date ?? world.calendar_date}
        </span>
      </header>

      {/* 3-column layout */}
      <div className="flex-1 grid grid-cols-[240px_1fr_280px] gap-3 p-3 overflow-hidden">
        <WorldPanel
          worldId={world.id}
          world={liveWorld ?? world}
          lastResult={lastResult}
          onSelectAgent={setSelectedAgentId}
          selectedAgentId={selectedAgentId}
          onResetWorld={() => setSelectedAgentId(null)}
        />

        <TimelinePanel
          worldId={world.id}
          lastResult={lastResult}
          onSelectAgent={setSelectedAgentId}
        />

        <AgentPanel
          worldId={world.id}
          agentId={selectedAgentId}
          lastResult={lastResult}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

export default function App() {
  const [activeWorld, setActiveWorld] = useState<World | null>(null);

  if (activeWorld) {
    return <Dashboard world={activeWorld} onBack={() => setActiveWorld(null)} />;
  }
  return <WorldSelector onSelect={setActiveWorld} />;
}
