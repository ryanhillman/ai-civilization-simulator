// VillageMap — static SVG village layout. Pure presentation, no simulation logic.
import { useMemo } from "react";
import type { AgentSummary, ResolvedAction } from "@/types";

// ---------------------------------------------------------------------------
// Palette — mirrors AgentAvatar.tsx
// ---------------------------------------------------------------------------

const PALETTE = [
  { bg: "#78350f", fg: "#fcd34d" },
  { bg: "#14532d", fg: "#6ee7b7" },
  { bg: "#1e3a8a", fg: "#93c5fd" },
  { bg: "#7f1d1d", fg: "#fca5a5" },
  { bg: "#4c1d95", fg: "#d8b4fe" },
  { bg: "#134e4a", fg: "#5eead4" },
  { bg: "#7c2d12", fg: "#fdba74" },
  { bg: "#1e1b4b", fg: "#a5b4fc" },
];

// ---------------------------------------------------------------------------
// Static layout
// ---------------------------------------------------------------------------

// Canvas expanded 100px in all directions for agent token clearance at all edges.
const W = 460;
const H = 420;

// Circular plaque radius for building nodes
const PLAQUE_R = 17;

// Building positions — shifted +90,+90 from original layout so that
// the minimum distance from any building center to the SVG edge is ≥ 110px,
// well clear of the 25px agent orbit radius + 9px token radius.
const BUILDINGS = [
  { id: "smithy", icon: "🔨", x: 129, y: 127, stroke: "#9a3412", fill: "#120806" },
  { id: "church", icon: "⛪", x: 331, y: 127, stroke: "#4338ca", fill: "#060610" },
  { id: "market", icon: "🎪", x: 230, y: 194, stroke: "#b45309", fill: "#110902" },
  { id: "homes",  icon: "🏠", x: 129, y: 259, stroke: "#57534e", fill: "#0b0b0a" },
  { id: "tavern", icon: "🍺", x: 331, y: 259, stroke: "#7c3aed", fill: "#0d0810" },
  { id: "farm",   icon: "🌾", x: 153, y: 311, stroke: "#15803d", fill: "#030c04" },
  { id: "green",  icon: "🌿", x: 268, y: 311, stroke: "#166534", fill: "#030c04" },
] as const;

// Road segments connecting building centers
const ROADS: [number, number, number, number][] = [
  [129, 127, 230, 194], // smithy → market
  [331, 127, 230, 194], // church → market
  [129, 259, 230, 194], // homes  → market
  [331, 259, 230, 194], // tavern → market
  [268, 311, 230, 194], // green  → market
  [153, 311, 129, 259], // farm   → homes
];

// ---------------------------------------------------------------------------
// Radial agent distribution — agents orbit their building in a full 360° circle
// starting at the 3 o'clock position.
// ---------------------------------------------------------------------------

const AGENT_RADIUS = 25; // px from building center

function radialOffset(index: number, total: number): { x: number; y: number } {
  const angle = (index * (360 / total)) * (Math.PI / 180);
  return {
    x: Math.cos(angle) * AGENT_RADIUS,
    y: Math.sin(angle) * AGENT_RADIUS,
  };
}

// ---------------------------------------------------------------------------
// Location resolution (exported for unit tests)
// ---------------------------------------------------------------------------

const ACTION_LOCATION: Readonly<Record<string, string>> = {
  harvest_food:  "farm",
  craft_tools:   "smithy",
  trade_goods:   "market",
  trade_food:    "market",
  pray:          "church",
  bless_village: "church",
  heal_self:     "homes",
  heal_agent:    "homes",
  steal_food:    "tavern",
  gossip:        "tavern",
  patrol:        "green",
  rest:          "homes",
};

const PROFESSION_DEFAULT: Readonly<Record<string, string>> = {
  farmer:     "farm",
  blacksmith: "smithy",
  merchant:   "market",
  healer:     "homes",
  priest:     "church",
  soldier:    "green",
};

// Action type -> icon shown above agent token
const ACTION_ICON: Readonly<Record<string, string>> = {
  trade_goods:   "\u2696",       // scales
  trade_food:    "\u2696",
  harvest_food:  "\uD83C\uDF3E", // sheaf
  craft_tools:   "\u2692",       // hammer
  gossip:        "\uD83D\uDCAC", // speech bubble
  steal_food:    "\uD83D\uDCAC",
  bless_village: "\u2736",       // six-pointed star
  pray:          "\u2736",
};

/** action_type → profession default → "green" fallback. Dead → "homes". */
export function resolveAgentLocation(
  profession: string,
  isAlive: boolean,
  action: Pick<ResolvedAction, "action_type"> | undefined,
): string {
  if (!isAlive) return "homes";
  return (action ? ACTION_LOCATION[action.action_type] : undefined)
    ?? PROFESSION_DEFAULT[profession]
    ?? "green";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const TOKEN_R = 9;

interface Props {
  agents: AgentSummary[];
  resolvedActions: ResolvedAction[] | null;
  selectedAgentId: number | null;
  onSelectAgent: (id: number) => void;
}

export default function VillageMap({
  agents,
  resolvedActions,
  selectedAgentId,
  onSelectAgent,
}: Props) {
  const actionByAgent = useMemo(() => {
    const m = new Map<number, ResolvedAction>();
    for (const a of resolvedActions ?? []) m.set(a.agent_id, a);
    return m;
  }, [resolvedActions]);

  const groups = useMemo(() => {
    const m = new Map<string, AgentSummary[]>();
    for (const b of BUILDINGS) m.set(b.id, []);
    for (const agent of agents) {
      const loc = resolveAgentLocation(agent.profession, agent.is_alive, actionByAgent.get(agent.id));
      m.get(loc)?.push(agent);
    }
    return m;
  }, [agents, actionByAgent]);

  return (
    <div className="panel h-full flex flex-col overflow-hidden">
      <div className="panel-header py-2">Village Map</div>
      <div className="flex flex-1 min-h-0 justify-center items-center p-4">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          style={{ width: "100%", height: "100%", maxWidth: W, display: "block" }}
          role="img"
          aria-label="Village map"
        >
          <defs>
            <radialGradient id="vm-bg" cx="50%" cy="45%" r="65%">
              <stop offset="0%" stopColor="#0e1f0e" />
              <stop offset="100%" stopColor="#050c05" />
            </radialGradient>
            <filter id="vm-shadow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#000" floodOpacity="0.8" />
            </filter>
            <filter id="vm-token-shadow" x="-50%" y="-50%" width="200%" height="200%">
              <feDropShadow dx="0" dy="2" stdDeviation="2" floodColor="#000" floodOpacity="0.5" />
            </filter>
          </defs>

          {/* Background */}
          <rect width={W} height={H} fill="url(#vm-bg)" rx={4} />

          {/* Roads */}
          {ROADS.map(([x1, y1, x2, y2], i) => (
            <path
              key={i}
              d={`M ${x1} ${y1} L ${x2} ${y2}`}
              stroke="#1c2e12"
              strokeWidth={9}
              strokeLinecap="round"
              strokeOpacity={0.6}
              fill="none"
            />
          ))}

          {/* Buildings — circular plaque with centered icon */}
          {BUILDINGS.map((b) => (
            <g key={b.id}>
              {/* Plaque shadow */}
              <circle
                cx={b.x} cy={b.y} r={PLAQUE_R}
                fill={b.fill}
                stroke={b.stroke}
                strokeWidth={1.5}
                filter="url(#vm-shadow)"
              />
              {/* Subtle inner ring */}
              <circle
                cx={b.x} cy={b.y} r={PLAQUE_R - 3}
                fill="none"
                stroke={b.stroke}
                strokeWidth={0.5}
                strokeOpacity={0.35}
              />
              {/* Building icon — centered exactly on building coordinate */}
              <text
                x={b.x} y={b.y}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={14}
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {b.icon}
              </text>
            </g>
          ))}

          {/* Agent token layer — rendered after all buildings so tokens are always on top.
              Selected agent is sorted last within its group (SVG z-order = highest). */}
          <g data-layer="agents">
          {BUILDINGS.map((b) => {
            const group = groups.get(b.id) ?? [];
            if (group.length === 0) return null;

            // Unselected agents first, selected last so it renders on top
            const sorted = [
              ...group.filter((a) => a.id !== selectedAgentId),
              ...group.filter((a) => a.id === selectedAgentId),
            ];

            return sorted.map((agent) => {
              // Deterministic slot from agent's position in the original (unsorted) group
              const slotIdx = group.findIndex((a) => a.id === agent.id);
              const { x: dx, y: dy } = radialOffset(slotIdx, group.length);
              const cx = b.x + dx;
              const cy = b.y + dy;

              const { bg } = PALETTE[agent.id % PALETTE.length];
              const isSelected = agent.id === selectedAgentId;
              const agentAction = actionByAgent.get(agent.id);
              const actionIcon =
                agent.is_alive && agent.is_sick
                  ? "\u2623" // biohazard
                  : agentAction
                  ? ACTION_ICON[agentAction.action_type]
                  : undefined;

              return (
                <g
                  key={agent.id}
                  onClick={() => onSelectAgent(agent.id)}
                  style={{ cursor: "pointer", ...(!agent.is_alive ? { filter: "grayscale(1)", opacity: 0.3 } : {}) }}
                  data-testid={`agent-token-${agent.id}`}
                >
                  <title>{agent.name} — {agent.profession}</title>

                  {/* Selection ring */}
                  {isSelected && (
                    <circle
                      cx={cx} cy={cy} r={TOKEN_R + 3.5}
                      fill="none"
                      stroke="#f59e0b"
                      strokeWidth={2}
                      data-testid={`agent-selected-${agent.id}`}
                    />
                  )}

                  {/* Token body */}
                  <circle
                    cx={cx} cy={cy} r={TOKEN_R}
                    fill={bg}
                    stroke={isSelected ? "#f59e0b" : "#0d1117"}
                    strokeWidth={2}
                    filter="url(#vm-token-shadow)"
                  />

                  {/* Subtle inner highlight */}
                  <ellipse
                    cx={cx - 2} cy={cy - 3} rx={4} ry={2.5}
                    fill="white" fillOpacity={0.07}
                    style={{ pointerEvents: "none" }}
                  />

                  {/* Action / status icon above token */}
                  {actionIcon && (
                    <text
                      x={cx} y={cy - TOKEN_R - 2}
                      textAnchor="middle"
                      dominantBaseline="auto"
                      fontSize={8}
                      style={{ pointerEvents: "none", userSelect: "none" }}
                    >
                      {actionIcon}
                    </text>
                  )}
                </g>
              );
            });
          })}

          </g>

          {agents.length === 0 && (
            <text
              x={W / 2} y={H / 2}
              textAnchor="middle"
              dominantBaseline="central"
              fill="#44403c"
              fontSize={9}
              fontFamily="Inter, system-ui, sans-serif"
            >
              Advance a turn to place villagers
            </text>
          )}
        </svg>
      </div>
    </div>
  );
}
