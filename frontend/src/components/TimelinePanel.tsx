import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { agentApi, timelineApi } from "@/api/client";
import type { TurnEventDomain, TurnEvent, TurnResult, WorldEvent } from "@/types";
import { AgentAvatar } from "./AgentAvatar";

// Extract the quoted rumor content from a gossip description, e.g.
// 'Aldric hears: "Elena stole food."' → 'Elena stole food.'
// Used to collapse multiple propagations of the same rumor into one row.
function gossipRumorKey(desc: string): string {
  const m = desc.match(/"(.+)"/);
  return m ? m[1] : desc;
}

interface GossipGroup {
  kind: "gossip_group";
  key: string;
  count: number;
  agentIds: number[];
}

interface CollapsedRoutine {
  kind: "collapsed_routine";
  agentId: number;
  eventType: string;
  count: number;
  startTurn: number;
  endTurn: number;
}

interface AgentInfo {
  name: string;
  is_alive: boolean;
  is_sick: boolean;
}

type AgentInfoMap = Record<number, AgentInfo>;

type LiveRow = TurnEventDomain | GossipGroup;
type HistoryRow = TurnEvent | GossipGroup;
type AugmentedHistoryRow = TurnEvent | GossipGroup | CollapsedRoutine;

// Gossip collapse — multiple propagations of the same rumor → single group row
function collapseGossipLive(events: TurnEventDomain[]): LiveRow[] {
  const result: LiveRow[] = [];
  const pending = new Map<string, GossipGroup>();

  function flushPending() {
    for (const g of pending.values()) result.push(g);
    pending.clear();
  }

  for (const e of events) {
    if (e.event_type === "gossip") {
      const key = gossipRumorKey(e.description);
      const existing = pending.get(key);
      if (existing) {
        existing.count += 1;
        existing.agentIds.push(...e.agent_ids.filter((id) => !existing.agentIds.includes(id)));
      } else {
        pending.set(key, { kind: "gossip_group", key, count: 1, agentIds: [...e.agent_ids] });
      }
    } else {
      flushPending();
      result.push(e);
    }
  }
  flushPending();
  return result;
}

function collapseGossipHistory(events: TurnEvent[]): HistoryRow[] {
  const result: HistoryRow[] = [];
  const pending = new Map<string, GossipGroup>();

  function flushPending() {
    for (const g of pending.values()) result.push(g);
    pending.clear();
  }

  for (const e of events) {
    if (e.event_type === "gossip") {
      const key = gossipRumorKey(e.description);
      const existing = pending.get(key);
      if (existing) {
        existing.count += 1;
        existing.agentIds.push(...e.agent_ids.filter((id) => !existing.agentIds.includes(id)));
      } else {
        pending.set(key, { kind: "gossip_group", key, count: 1, agentIds: [...e.agent_ids] });
      }
    } else {
      flushPending();
      result.push(e);
    }
  }
  flushPending();
  return result;
}

// ---------------------------------------------------------------------------
// Routine collapse — consecutive same-action streaks from the same agent
// are collapsed into a single summary row when they span ≥ 3 turns.
// ---------------------------------------------------------------------------

const ROUTINE_EVENT_TYPES_SET = new Set(["harvest", "festival"]);
const ROUTINE_COLLAPSE_THRESHOLD = 3;

function collapseRoutineHistory(
  groupedHistory: [number, TurnEvent[]][]
): [number, AugmentedHistoryRow[]][] {
  // Process oldest-first for streak detection
  const sorted = [...groupedHistory].sort((a, b) => a[0] - b[0]);

  type StreakState = { eventType: string; startTurn: number; lastTurn: number; ids: number[] };
  const active = new Map<number, StreakState>(); // agentId → current streak

  type CompletedStreak = {
    agentId: number;
    eventType: string;
    startTurn: number;
    endTurn: number;
    ids: Set<number>;
  };
  const completed: CompletedStreak[] = [];

  const flushStreak = (agentId: number) => {
    const s = active.get(agentId);
    if (s && s.ids.length >= ROUTINE_COLLAPSE_THRESHOLD) {
      completed.push({
        agentId,
        eventType: s.eventType,
        startTurn: s.startTurn,
        endTurn: s.lastTurn,
        ids: new Set(s.ids),
      });
    }
    active.delete(agentId);
  };

  for (const [turn, events] of sorted) {
    // Identify routine events per agent this turn
    const routineThisTurn = new Map<number, TurnEvent>();
    for (const e of events) {
      if (ROUTINE_EVENT_TYPES_SET.has(e.event_type) && e.agent_ids.length > 0) {
        routineThisTurn.set(e.agent_ids[0], e);
      }
    }

    // End streaks that don't continue into this turn
    for (const [agentId, streak] of [...active.entries()]) {
      const cur = routineThisTurn.get(agentId);
      if (!cur || cur.event_type !== streak.eventType || turn !== streak.lastTurn + 1) {
        flushStreak(agentId);
      }
    }

    // Extend or start streaks for routine events this turn
    for (const [agentId, event] of routineThisTurn) {
      const existing = active.get(agentId);
      if (existing) {
        existing.lastTurn = turn;
        existing.ids.push(event.id);
      } else {
        active.set(agentId, {
          eventType: event.event_type,
          startTurn: turn,
          lastTurn: turn,
          ids: [event.id],
        });
      }
    }
  }

  // Flush any still-active streaks at end of data
  for (const agentId of [...active.keys()]) flushStreak(agentId);

  // Build suppression set (event IDs to hide) and injection map (collapsed rows per turn)
  const suppressed = new Set<number>();
  const injectAt = new Map<number, CollapsedRoutine[]>();

  for (const s of completed) {
    for (const id of s.ids) suppressed.add(id);
    const arr = injectAt.get(s.endTurn) ?? [];
    arr.push({
      kind: "collapsed_routine",
      agentId: s.agentId,
      eventType: s.eventType,
      count: s.ids.size,
      startTurn: s.startTurn,
      endTurn: s.endTurn,
    });
    injectAt.set(s.endTurn, arr);
  }

  // Build final per-turn row arrays; skip turns that become empty
  const result: [number, AugmentedHistoryRow[]][] = [];
  for (const [turn, events] of sorted) {
    const rows: AugmentedHistoryRow[] = [];

    // Collapsed summaries anchored at endTurn
    for (const c of injectAt.get(turn) ?? []) rows.push(c);

    // Non-suppressed events (gossip-collapsed)
    for (const row of collapseGossipHistory(events)) {
      if ("kind" in row) {
        rows.push(row); // GossipGroup — never suppressed
      } else if (!suppressed.has(row.id)) {
        rows.push(row);
      }
    }

    if (rows.length > 0) result.push([turn, rows]);
  }

  // Re-sort newest-first for display
  return result.sort((a, b) => b[0] - a[0]);
}

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

const EVENT_ICON: Record<string, string> = {
  trade: "⚖",
  harvest: "⬡",
  heal: "✚",
  theft: "◈",
  conflict: "✕",
  festival: "✦",
  sickness: "⊙",
  weather: "◎",
  gossip: "❧",
  rest: "○",
};

const WORLD_EVENT_COLOR: Record<string, string> = {
  festival: "border-amber-600 bg-amber-950/40",
  poor_harvest: "border-orange-700 bg-orange-950/40",
  storm: "border-sky-700 bg-sky-950/40",
  sickness_outbreak: "border-red-700 bg-red-950/40",
};

// Mirrors backend calendar.py — turn 0 = March 1, Year 1 (day 59 of a 365-day year)
function turnToShortDate(turn: number): string {
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const daysSinceEpoch = turn + 59; // March 1 = day-of-year index 59
  const year = Math.floor(daysSinceEpoch / 365) + 1;
  const dayOfYear = daysSinceEpoch % 365;
  let month = 0;
  let rem = dayOfYear;
  while (rem >= MONTH_DAYS[month]) {
    rem -= MONTH_DAYS[month++];
  }
  return `${MONTHS[month]} ${rem + 1}, Yr ${year}`;
}

function AgentChip({
  id,
  agentInfoMap,
  agentNameMap,
  onSelectAgent,
  dim = false,
}: {
  id: number;
  agentInfoMap: AgentInfoMap;
  agentNameMap: Record<number, string>;
  onSelectAgent: (id: number) => void;
  dim?: boolean;
}) {
  const info = agentInfoMap[id];
  const name = agentNameMap[id] ?? `#${id}`;
  const btnCls = dim
    ? "text-stone-600 hover:text-stone-400"
    : "text-stone-500 hover:text-stone-300";
  return (
    <button
      className={`flex items-center gap-1 text-xs underline underline-offset-2 ${btnCls}`}
      onClick={() => onSelectAgent(id)}
    >
      {info && (
        <AgentAvatar
          id={id}
          name={info.name}
          isAlive={info.is_alive}
          size={14}
        />
      )}
      <span>{name}</span>
    </button>
  );
}

// Negative-rumor keywords that imply a trust/relationship hit
const _NEGATIVE_RUMOR = /hoard|stole|steal|theft|robbed|betray|cheat/i;

function GossipGroupRow({
  group,
  agentNameMap,
  agentInfoMap,
  onSelectAgent,
  dim = false,
}: {
  group: GossipGroup;
  agentNameMap: Record<number, string>;
  agentInfoMap: AgentInfoMap;
  onSelectAgent: (id: number) => void;
  dim?: boolean;
}) {
  const isNegative = _NEGATIVE_RUMOR.test(group.key);
  const textCls = dim ? "text-stone-500" : "text-stone-300";
  // Gossip always gets a purple left-border accent; negative rumors get a red trust badge
  const borderCls = dim
    ? "border-stone-800/40 border-l-2 border-l-purple-800/40 hover:bg-purple-950/10"
    : "border-stone-800/60 border-l-2 border-l-purple-600 bg-purple-950/20 hover:bg-purple-900/25";
  return (
    <div className={`px-4 py-2 border-b ${borderCls}`}>
      <div className="flex items-start gap-2">
        <span className="text-xs font-mono mt-0.5 shrink-0 text-purple-400" aria-hidden="true">❧</span>
        <span className="text-xs font-mono mt-0.5 shrink-0 text-purple-400 uppercase">gossip</span>
        <span className={`text-xs ${textCls} leading-relaxed`}>
          {group.count === 1 ? "1 villager heard" : `${group.count} villagers heard`}:{" "}
          <span className="italic">"{group.key}"</span>
        </span>
        {isNegative && (
          <span className="shrink-0 text-xs text-red-400 font-medium ml-0.5" title="Relationship impact">
            ↓ trust
          </span>
        )}
      </div>
      {group.agentIds.length > 0 && (
        <div className="flex gap-1.5 mt-1 ml-7 flex-wrap">
          {group.agentIds.map((id) => (
            <AgentChip
              key={id}
              id={id}
              agentInfoMap={agentInfoMap}
              agentNameMap={agentNameMap}
              onSelectAgent={onSelectAgent}
              dim={dim}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Drama event types that get highlighted styling in the timeline
const _DRAMA_TYPES = new Set(["sickness", "theft", "conflict"]);

function DeathBanner({
  description,
  agentIds,
  agentNameMap,
  agentInfoMap,
  onSelectAgent,
  dim = false,
}: {
  description: string;
  agentIds: number[];
  agentNameMap: Record<number, string>;
  agentInfoMap: AgentInfoMap;
  onSelectAgent: (id: number) => void;
  dim?: boolean;
}) {
  const containerCls = dim
    ? "mx-3 my-1.5 px-3 py-2 rounded border border-red-900/50 bg-red-950/20"
    : "mx-3 my-2 px-3 py-2.5 rounded border border-red-700 bg-red-950/40";
  const headingCls = dim ? "text-red-700" : "text-red-300";
  const textCls = dim ? "text-red-900/80" : "text-red-200/80";
  return (
    <div className={containerCls}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-xs font-semibold uppercase tracking-wide ${headingCls}`}>✝ Death</span>
      </div>
      <p className={`text-xs leading-relaxed ${textCls}`}>{description}</p>
      {agentIds.length > 0 && (
        <div className="flex gap-1.5 mt-1.5 flex-wrap">
          {agentIds.map((id) => (
            <AgentChip
              key={id}
              id={id}
              agentInfoMap={agentInfoMap}
              agentNameMap={agentNameMap}
              onSelectAgent={onSelectAgent}
              dim={dim}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function EventRow({
  event,
  agentNameMap,
  agentInfoMap,
  onSelectAgent,
}: {
  event: TurnEventDomain;
  agentNameMap: Record<number, string>;
  agentInfoMap: AgentInfoMap;
  onSelectAgent: (id: number) => void;
}) {
  if (event.details?.is_death === true) {
    return (
      <DeathBanner
        description={event.description}
        agentIds={event.agent_ids}
        agentNameMap={agentNameMap}
        agentInfoMap={agentInfoMap}
        onSelectAgent={onSelectAgent}
      />
    );
  }
  const color = EVENT_COLOR[event.event_type] ?? "text-stone-400";
  const icon = EVENT_ICON[event.event_type] ?? "·";
  const isDrama = _DRAMA_TYPES.has(event.event_type);
  const containerCls = isDrama
    ? "px-4 py-2.5 border-b border-stone-800/60 border-l-2 border-l-orange-600 bg-orange-950/20 hover:bg-orange-900/25"
    : "px-4 py-2.5 border-b border-stone-800/60 hover:bg-stone-800/40";
  return (
    <div className={containerCls}>
      <div className="flex items-start gap-2">
        <span className={`text-xs font-mono mt-0.5 shrink-0 ${color}`} aria-hidden="true">
          {icon}
        </span>
        <span className={`text-xs font-mono mt-0.5 shrink-0 ${color} uppercase`}>
          {event.event_type}
        </span>
        <span className="text-xs text-stone-300 leading-relaxed">{event.description}</span>
      </div>
      {event.agent_ids.length > 0 && (
        <div className="flex gap-1.5 mt-1 ml-7 flex-wrap">
          {event.agent_ids.map((id) => (
            <AgentChip
              key={id}
              id={id}
              agentInfoMap={agentInfoMap}
              agentNameMap={agentNameMap}
              onSelectAgent={onSelectAgent}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function DbEventRow({
  event,
  agentNameMap,
  agentInfoMap,
  onSelectAgent,
}: {
  event: TurnEvent;
  agentNameMap: Record<number, string>;
  agentInfoMap: AgentInfoMap;
  onSelectAgent: (id: number) => void;
}) {
  if (event.details?.is_death === true) {
    return (
      <DeathBanner
        description={event.description}
        agentIds={event.agent_ids}
        agentNameMap={agentNameMap}
        agentInfoMap={agentInfoMap}
        onSelectAgent={onSelectAgent}
        dim
      />
    );
  }
  const color = EVENT_COLOR[event.event_type] ?? "text-stone-500";
  const icon = EVENT_ICON[event.event_type] ?? "·";
  const isDrama = _DRAMA_TYPES.has(event.event_type);
  const containerCls = isDrama
    ? "px-4 py-2 border-b border-stone-800/40 border-l-2 border-l-orange-700/60 bg-orange-950/10 hover:bg-orange-950/20"
    : "px-4 py-2 border-b border-stone-800/40 hover:bg-stone-800/20";
  return (
    <div className={containerCls}>
      <div className="flex items-start gap-2">
        <span className={`text-xs font-mono mt-0.5 shrink-0 ${color}`} aria-hidden="true">
          {icon}
        </span>
        <span className={`text-xs font-mono shrink-0 uppercase ${color}`}>
          {event.event_type}
        </span>
        <span className="text-xs text-stone-500">{event.description}</span>
      </div>
      {event.agent_ids.length > 0 && (
        <div className="flex gap-1.5 mt-1 ml-7 flex-wrap">
          {event.agent_ids.map((id) => (
            <AgentChip
              key={id}
              id={id}
              agentInfoMap={agentInfoMap}
              agentNameMap={agentNameMap}
              onSelectAgent={onSelectAgent}
              dim
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CollapsedRoutineRow({
  row,
  agentNameMap,
  agentInfoMap,
  onSelectAgent,
  dim = false,
}: {
  row: CollapsedRoutine;
  agentNameMap: Record<number, string>;
  agentInfoMap: AgentInfoMap;
  onSelectAgent: (id: number) => void;
  dim?: boolean;
}) {
  const name = agentNameMap[row.agentId] ?? `#${row.agentId}`;
  const icon = row.eventType === "harvest" ? "⬡" : "✦";
  const color = row.eventType === "harvest" ? "text-green-700" : "text-amber-700";
  const description =
    row.eventType === "harvest"
      ? `${name} spent ${row.count} days harvesting in the fields.`
      : `${name} offered blessings for ${row.count} consecutive days.`;
  const textCls = dim ? "text-stone-600" : "text-stone-500";
  const borderCls = dim
    ? "border-stone-800/30 hover:bg-stone-800/15"
    : "border-stone-800/50 hover:bg-stone-800/25";

  return (
    <div className={`px-4 py-1.5 border-b ${borderCls}`}>
      <div className="flex items-center gap-2">
        <span className={`text-xs font-mono shrink-0 ${color}`}>{icon}</span>
        {agentInfoMap[row.agentId] && (
          <AgentAvatar
            id={row.agentId}
            name={agentInfoMap[row.agentId].name}
            isAlive={agentInfoMap[row.agentId].is_alive}
            size={14}
          />
        )}
        <span
          className={`text-xs italic ${textCls} cursor-pointer hover:text-stone-400`}
          onClick={() => onSelectAgent(row.agentId)}
        >
          {description}
        </span>
      </div>
    </div>
  );
}

function WorldEventBanner({ we }: { we: WorldEvent }) {
  const cls = WORLD_EVENT_COLOR[we.event_type] ?? "border-stone-600 bg-stone-800/40";
  return (
    <div className={`mx-3 my-2 px-3 py-2 rounded border text-xs ${cls}`}>
      <span className="font-semibold uppercase text-stone-300">{we.event_type.replace(/_/g, " ")}</span>
      <span className="text-stone-400 ml-2">{we.description}</span>
    </div>
  );
}

export default function TimelinePanel({ worldId, lastResult, onSelectAgent }: Props) {
  const { data: dbEvents } = useQuery({
    queryKey: ["timeline", worldId],
    queryFn: () => timelineApi.list(worldId, { limit: 100 }),
  });

  // Agents list for name resolution — shared cache with WorldPanel
  const { data: dbAgents } = useQuery({
    queryKey: ["agents", worldId],
    queryFn: () => agentApi.list(worldId),
  });

  // Build agent ID → name map (live result takes priority over DB list)
  const agentNameMap = useMemo(() => {
    const map: Record<number, string> = {};
    dbAgents?.forEach((a) => { map[a.id] = a.name; });
    lastResult?.agents.forEach((a) => { map[a.id] = a.name; });
    return map;
  }, [dbAgents, lastResult]);

  // Build agent ID → portrait info map for inline avatar chips
  const agentInfoMap = useMemo<AgentInfoMap>(() => {
    const map: AgentInfoMap = {};
    dbAgents?.forEach((a) => {
      map[a.id] = { name: a.name, is_alive: a.is_alive, is_sick: a.is_sick };
    });
    lastResult?.agents.forEach((a) => {
      map[a.id] = { name: a.name, is_alive: a.is_alive, is_sick: a.is_sick };
    });
    return map;
  }, [dbAgents, lastResult]);

  // Group DB events by turn (newest first), excluding current live turn
  const groupedHistory = useMemo(() => {
    const cutoff = lastResult ? lastResult.turn_number : Infinity;
    const filtered = (dbEvents ?? []).filter((e) => e.turn_number < cutoff);
    const groups = new Map<number, TurnEvent[]>();
    for (const e of filtered) {
      const arr = groups.get(e.turn_number) ?? [];
      arr.push(e);
      groups.set(e.turn_number, arr);
    }
    return [...groups.entries()].sort((a, b) => b[0] - a[0]);
  }, [dbEvents, lastResult]);

  // Apply routine collapse across turns (3+ consecutive same-action → summary)
  const augmentedHistory = useMemo(() => collapseRoutineHistory(groupedHistory), [groupedHistory]);

  const showLive = lastResult !== null && lastResult.events.length > 0;

  // Pre-compute live turn rows outside JSX to avoid inline IIFE syntax issues
  const liveRows: LiveRow[] = useMemo(() => {
    if (!lastResult) return [];
    const bannerDescs = new Set(lastResult.world_events.map((we) => we.description));
    const filteredEvents = lastResult.events.filter((e) => !bannerDescs.has(e.description));
    return collapseGossipLive(filteredEvents);
  }, [lastResult]);

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="panel-header">
        Chronicle
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

            {/* Current turn header */}
            <div className="px-4 py-1.5 text-xs text-stone-500 border-b border-stone-800/60 bg-stone-900/60 flex items-center gap-2">
              <span className="font-semibold text-stone-400">Turn {lastResult.turn_number}</span>
              <span className="text-stone-600">{lastResult.calendar_date.split(" — ")[0]}</span>
            </div>

            {/* Turn events — filter out entries already shown as world-event banners above */}
            {liveRows.length === 0 ? (
              <p className="px-4 py-4 text-xs text-stone-600">No events this turn.</p>
            ) : (
              liveRows.map((row, i) =>
                "kind" in row ? (
                  <GossipGroupRow
                    key={i}
                    group={row}
                    agentNameMap={agentNameMap}
                    agentInfoMap={agentInfoMap}
                    onSelectAgent={onSelectAgent}
                  />
                ) : (
                  <EventRow
                    key={i}
                    event={row}
                    agentNameMap={agentNameMap}
                    agentInfoMap={agentInfoMap}
                    onSelectAgent={onSelectAgent}
                  />
                )
              )
            )}

            {/* Historical section */}
            {augmentedHistory.length > 0 && (
              <div className="px-4 py-1.5 text-xs text-stone-600 border-y border-stone-800 bg-stone-900/80 mt-1">
                Earlier turns
              </div>
            )}
            {augmentedHistory.map(([turn, rows]) => (
              <div key={turn}>
                <div className="px-4 py-1 text-xs bg-stone-900/40 border-b border-stone-800/40 flex items-center gap-2">
                  <span className="text-stone-600 font-mono font-semibold">T{turn}</span>
                  <span className="text-stone-700">{turnToShortDate(turn)}</span>
                </div>
                {rows.map((row, i) => {
                  if ("kind" in row && row.kind === "collapsed_routine") {
                    return (
                      <CollapsedRoutineRow
                        key={`cr-${i}`}
                        row={row}
                        agentNameMap={agentNameMap}
                        agentInfoMap={agentInfoMap}
                        onSelectAgent={onSelectAgent}
                        dim
                      />
                    );
                  }
                  if ("kind" in row) {
                    return (
                      <GossipGroupRow
                        key={i}
                        group={row}
                        agentNameMap={agentNameMap}
                        agentInfoMap={agentInfoMap}
                        onSelectAgent={onSelectAgent}
                        dim
                      />
                    );
                  }
                  return (
                    <DbEventRow
                      key={row.id}
                      event={row}
                      agentNameMap={agentNameMap}
                      agentInfoMap={agentInfoMap}
                      onSelectAgent={onSelectAgent}
                    />
                  );
                })}
              </div>
            ))}
          </>
        ) : dbEvents && dbEvents.length > 0 ? (
          // No live result — show full DB timeline grouped by turn
          <>
            {augmentedHistory.map(([turn, rows]) => (
              <div key={turn}>
                <div className="px-4 py-1 text-xs bg-stone-900/40 border-b border-stone-800/40 flex items-center gap-2">
                  <span className="text-stone-600 font-mono font-semibold">T{turn}</span>
                  <span className="text-stone-700">{turnToShortDate(turn)}</span>
                </div>
                {rows.map((row, i) => {
                  if ("kind" in row && row.kind === "collapsed_routine") {
                    return (
                      <CollapsedRoutineRow
                        key={`cr-${i}`}
                        row={row}
                        agentNameMap={agentNameMap}
                        agentInfoMap={agentInfoMap}
                        onSelectAgent={onSelectAgent}
                        dim
                      />
                    );
                  }
                  if ("kind" in row) {
                    return (
                      <GossipGroupRow
                        key={i}
                        group={row}
                        agentNameMap={agentNameMap}
                        agentInfoMap={agentInfoMap}
                        onSelectAgent={onSelectAgent}
                        dim
                      />
                    );
                  }
                  return (
                    <DbEventRow
                      key={row.id}
                      event={row}
                      agentNameMap={agentNameMap}
                      agentInfoMap={agentInfoMap}
                      onSelectAgent={onSelectAgent}
                    />
                  );
                })}
              </div>
            ))}
          </>
        ) : (
          <p className="px-4 py-6 text-xs text-stone-600 text-center">
            No events yet. Advance a turn to begin.
          </p>
        )}
      </div>
    </div>
  );
}
