import { useQuery } from "@tanstack/react-query";
import { timelineApi } from "@/api/client";
import type { TurnEventDomain, TurnResult, WorldEvent } from "@/types";

interface Props {
  worldId: number;
  lastResult: TurnResult | null;
  onSelectAgent: (agentId: number) => void;
}

const EVENT_COLOR: Record<string, string> = {
  trade: "text-emerald-400",
  harvest: "text-green-400",
  heal: "text-teal-400",
  theft: "text-red-400",
  conflict: "text-red-500",
  festival: "text-amber-400",
  sickness: "text-orange-400",
  weather: "text-sky-400",
  gossip: "text-purple-400",
  rest: "text-stone-400",
};

const WORLD_EVENT_COLOR: Record<string, string> = {
  festival: "border-amber-600 bg-amber-950/40",
  poor_harvest: "border-orange-700 bg-orange-950/40",
  storm: "border-sky-700 bg-sky-950/40",
  sickness_outbreak: "border-red-700 bg-red-950/40",
};

function EventRow({
  event,
  onSelectAgent,
}: {
  event: TurnEventDomain;
  onSelectAgent: (id: number) => void;
}) {
  const color = EVENT_COLOR[event.event_type] ?? "text-stone-400";
  return (
    <div className="px-4 py-2 border-b border-stone-800/60 hover:bg-stone-800/40 group">
      <div className="flex items-start gap-2">
        <span className={`text-xs font-mono mt-0.5 shrink-0 ${color} uppercase`}>
          {event.event_type}
        </span>
        <span className="text-xs text-stone-300 leading-relaxed">{event.description}</span>
      </div>
      {event.agent_ids.length > 0 && (
        <div className="flex gap-1 mt-1 ml-0">
          {event.agent_ids.map((id) => (
            <button
              key={id}
              className="text-xs text-stone-500 hover:text-stone-300 underline"
              onClick={() => onSelectAgent(id)}
            >
              #{id}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function WorldEventBanner({ we }: { we: WorldEvent }) {
  const cls = WORLD_EVENT_COLOR[we.event_type] ?? "border-stone-600 bg-stone-800/40";
  return (
    <div className={`mx-3 my-2 px-3 py-2 rounded border text-xs ${cls}`}>
      <span className="font-semibold uppercase text-stone-300">{we.event_type.replace("_", " ")}</span>
      <span className="text-stone-400 ml-2">{we.description}</span>
    </div>
  );
}

export default function TimelinePanel({ worldId, lastResult, onSelectAgent }: Props) {
  const { data: dbEvents } = useQuery({
    queryKey: ["timeline", worldId],
    queryFn: () => timelineApi.list(worldId, { limit: 100 }),
  });

  // Show last turn's events inline from TurnResult for immediate feedback,
  // falling back to DB timeline
  const showLive = lastResult !== null && lastResult.events.length > 0;

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">
        Timeline
        {lastResult && (
          <span className="ml-2 text-amber-400 normal-case text-xs font-normal">
            {lastResult.calendar_date}
          </span>
        )}
      </div>

      <div className="overflow-y-auto flex-1">
        {showLive ? (
          <>
            {/* AI narrative summary (multi-turn runs only) */}
            {lastResult.ai_summary && (
              <div className="mx-3 my-2 px-3 py-2.5 rounded border border-amber-800/60 bg-amber-950/30">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
                    Chronicle
                  </span>
                  <span className="text-xs text-stone-600">(AI narrative)</span>
                </div>
                <p className="text-xs text-amber-200/80 leading-relaxed italic">
                  {lastResult.ai_summary}
                </p>
              </div>
            )}

            {/* World events for this turn */}
            {lastResult.world_events.map((we, i) => (
              <WorldEventBanner key={i} we={we} />
            ))}

            {/* Turn events */}
            {lastResult.events.length === 0 ? (
              <p className="px-4 py-4 text-xs text-stone-600">No events this turn.</p>
            ) : (
              lastResult.events.map((e, i) => (
                <EventRow key={i} event={e} onSelectAgent={onSelectAgent} />
              ))
            )}

            {/* Separator */}
            {dbEvents && dbEvents.length > 0 && (
              <div className="px-4 py-2 text-xs text-stone-600 border-b border-stone-800 bg-stone-900/60">
                Earlier turns
              </div>
            )}

            {/* DB history — skip events from the current live turn */}
            {dbEvents
              ?.filter((e) => e.turn_number < lastResult.turn_number)
              .map((e) => (
                <div
                  key={e.id}
                  className="px-4 py-2 border-b border-stone-800/40 hover:bg-stone-800/20"
                >
                  <div className="flex items-start gap-2">
                    <span className="text-xs font-mono text-stone-600 shrink-0">
                      T{e.turn_number}
                    </span>
                    <span className={`text-xs font-mono shrink-0 uppercase ${EVENT_COLOR[e.event_type] ?? "text-stone-500"}`}>
                      {e.event_type}
                    </span>
                    <span className="text-xs text-stone-500">{e.description}</span>
                  </div>
                </div>
              ))}
          </>
        ) : dbEvents && dbEvents.length > 0 ? (
          dbEvents.map((e) => (
            <div
              key={e.id}
              className="px-4 py-2 border-b border-stone-800/40 hover:bg-stone-800/20"
            >
              <div className="flex items-start gap-2">
                <span className="text-xs font-mono text-stone-600 shrink-0">
                  T{e.turn_number}
                </span>
                <span
                  className={`text-xs font-mono shrink-0 uppercase ${
                    EVENT_COLOR[e.event_type] ?? "text-stone-500"
                  }`}
                >
                  {e.event_type}
                </span>
                <span className="text-xs text-stone-500">{e.description}</span>
              </div>
            </div>
          ))
        ) : (
          <p className="px-4 py-6 text-xs text-stone-600 text-center">
            No events yet. Advance a turn to begin.
          </p>
        )}
      </div>
    </div>
  );
}
