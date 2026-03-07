import { useQuery } from "@tanstack/react-query";
import { systemApi } from "@/api/client";

export default function App() {
  const { data: health, isError } = useQuery({
    queryKey: ["health"],
    queryFn: systemApi.health,
    retry: false,
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

      <div className="panel px-6 py-4 text-sm text-center">
        {health ? (
          <span className="text-green-400">
            Backend connected &mdash; env: <strong>{health.env}</strong>
          </span>
        ) : isError ? (
          <span className="text-red-400">
            Backend unreachable &mdash; is the FastAPI server running?
          </span>
        ) : (
          <span className="text-stone-500">Checking backend&hellip;</span>
        )}
      </div>

      <p className="text-stone-600 text-xs">
        Dashboard UI coming in Phase 5.
      </p>
    </div>
  );
}
