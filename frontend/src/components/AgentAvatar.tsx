// Deterministic portrait SVG avatar — no backend, no storage.
// All facial features (skin tone, hair style, hair color) derived from
// the numeric agent id; output is stable across reloads.

const PALETTE = [
  { bg: "#78350f", shoulder: "#3c1a07", fg: "#fcd34d" },
  { bg: "#14532d", shoulder: "#0a2916", fg: "#6ee7b7" },
  { bg: "#1e3a8a", shoulder: "#0f1d47", fg: "#93c5fd" },
  { bg: "#7f1d1d", shoulder: "#3f0e0e", fg: "#fca5a5" },
  { bg: "#4c1d95", shoulder: "#260e4a", fg: "#d8b4fe" },
  { bg: "#134e4a", shoulder: "#092726", fg: "#5eead4" },
  { bg: "#7c2d12", shoulder: "#3e1609", fg: "#fdba74" },
  { bg: "#1e1b4b", shoulder: "#0f0e26", fg: "#a5b4fc" },
];

const SKIN_TONES = [
  "#f5cba7", // light
  "#e8a87c", // medium-light
  "#c68642", // medium
  "#8d5524", // medium-dark
  "#5c3317", // dark
];

const HAIR_COLORS = [
  "#1a0800", // near-black
  "#3d2314", // dark brown
  "#7b4a1e", // medium brown
  "#c8a87a", // blonde
  "#a83c32", // auburn
  "#9c9c8f", // grey
];

/** Deterministic integer in [0, mod) from agent id + a per-feature salt. */
function det(id: number, salt: number, mod: number): number {
  return ((id * 2654435761 + salt * 40503) >>> 0) % mod;
}

// Hair is rendered BEFORE the face ellipse so the face naturally occludes
// the lower portion — only the top/sides peek out as visible hair.
function HairShape({ style, color }: { style: number; color: string }) {
  switch (style) {
    case 0: // Short oval cap
      return <ellipse cx="16" cy="8" rx="6.5" ry="4" fill={color} />;
    case 1: // Rounded arch — medium coverage
      return <path d="M 9.5 16 Q 9.5 5 16 5 Q 22.5 5 22.5 16" fill={color} />;
    case 2: // Close-cropped flat band
      return <ellipse cx="16" cy="7.5" rx="7" ry="3" fill={color} />;
    case 3: // Long — arch extends down the sides
      return <path d="M 8.5 22 Q 8.5 4 16 4 Q 23.5 4 23.5 22" fill={color} />;
    case 4: // Wide hood
      return <path d="M 7 18 Q 7 3 16 3 Q 25 3 25 18" fill={color} />;
    default:
      return null;
  }
}

interface AgentAvatarProps {
  id: number;
  name: string;
  isAlive?: boolean;
  isSick?: boolean;
  size?: number;
}

export function AgentAvatar({
  id,
  name,
  isAlive = true,
  isSick = false,
  size = 32,
}: AgentAvatarProps) {
  const { bg, shoulder } = PALETTE[id % PALETTE.length];
  const skin = SKIN_TONES[det(id, 3, 5)];
  const hairColor = HAIR_COLORS[det(id, 7, 6)];
  const hairStyle = det(id, 11, 5);

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size, boxSizing: "border-box", filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.5))" }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        xmlns="http://www.w3.org/2000/svg"
        aria-label={`${name} avatar`}
        style={!isAlive ? { filter: "grayscale(1) opacity(0.5)" } : undefined}
      >
        {/* Background — must be FIRST circle element; palette fill checked by determinism tests */}
        <circle cx="16" cy="16" r="15" fill={bg} />

        {/* Subtle top highlight */}
        <ellipse cx="13" cy="10" rx="6" ry="4" fill="white" fillOpacity="0.06" />

        {/* Shoulder suggestion — visible at the circle's lower edge */}
        <ellipse cx="16" cy="30" rx="11" ry="7" fill={shoulder} />

        {/* Hair — behind face, peeks out above and beside face edges */}
        <HairShape style={hairStyle} color={hairColor} />

        {/* Face */}
        <ellipse cx="16" cy="14.5" rx="6.5" ry="7.5" fill={skin} />

        {/* Eyes */}
        <circle cx="13.7" cy="13.5" r="0.85" fill="#1a0a00" fillOpacity="0.7" />
        <circle cx="18.3" cy="13.5" r="0.85" fill="#1a0a00" fillOpacity="0.7" />

        {/* Thin inner highlight ring */}
        <circle cx="16" cy="16" r="14.5" fill="none" stroke="white" strokeWidth="0.5" strokeOpacity="0.12" />

        {/* Sticker border — dark 2px outline that matches the map background,
            creating a cut-out effect that makes the avatar pop on dark surfaces */}
        <circle cx="16" cy="16" r="14" fill="none" stroke="#0d1117" strokeWidth="2" />
      </svg>

      {isSick && (
        <span
          className="absolute bottom-0 right-0 block w-2.5 h-2.5 rounded-full bg-red-500 ring-1 ring-stone-900"
          aria-label="sick indicator"
        />
      )}
    </div>
  );
}
