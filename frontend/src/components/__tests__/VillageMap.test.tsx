import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import VillageMap, { resolveAgentLocation } from "../VillageMap";
import type { AgentSummary, ResolvedAction } from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function action(type: string): Pick<ResolvedAction, "action_type"> {
  return { action_type: type };
}

const BASE_AGENT: AgentSummary = {
  id: 1,
  name: "Aldric",
  profession: "farmer",
  age: 30,
  is_alive: true,
  is_sick: false,
  hunger: 0,
};

// ---------------------------------------------------------------------------
// resolveAgentLocation — pure function
// ---------------------------------------------------------------------------

describe("resolveAgentLocation", () => {
  it("maps harvest_food → farm", () => {
    expect(resolveAgentLocation("farmer", true, action("harvest_food"))).toBe("farm");
  });

  it("maps craft_tools → smithy", () => {
    expect(resolveAgentLocation("blacksmith", true, action("craft_tools"))).toBe("smithy");
  });

  it("maps trade_goods and trade_food → market", () => {
    expect(resolveAgentLocation("merchant", true, action("trade_goods"))).toBe("market");
    expect(resolveAgentLocation("farmer", true, action("trade_food"))).toBe("market");
  });

  it("maps pray and bless_village → church", () => {
    expect(resolveAgentLocation("priest", true, action("pray"))).toBe("church");
    expect(resolveAgentLocation("priest", true, action("bless_village"))).toBe("church");
  });

  it("maps heal_self and heal_agent → homes", () => {
    expect(resolveAgentLocation("healer", true, action("heal_self"))).toBe("homes");
    expect(resolveAgentLocation("healer", true, action("heal_agent"))).toBe("homes");
  });

  it("maps rest → homes", () => {
    expect(resolveAgentLocation("farmer", true, action("rest"))).toBe("homes");
  });

  it("maps patrol → green", () => {
    expect(resolveAgentLocation("soldier", true, action("patrol"))).toBe("green");
  });

  it("maps gossip and steal_food → tavern", () => {
    expect(resolveAgentLocation("merchant", true, action("gossip"))).toBe("tavern");
    expect(resolveAgentLocation("farmer", true, action("steal_food"))).toBe("tavern");
  });

  it("uses profession default when action is undefined", () => {
    expect(resolveAgentLocation("farmer", true, undefined)).toBe("farm");
    expect(resolveAgentLocation("blacksmith", true, undefined)).toBe("smithy");
    expect(resolveAgentLocation("merchant", true, undefined)).toBe("market");
    expect(resolveAgentLocation("healer", true, undefined)).toBe("homes");
    expect(resolveAgentLocation("priest", true, undefined)).toBe("church");
    expect(resolveAgentLocation("soldier", true, undefined)).toBe("green");
  });

  it("overrides profession default with action type", () => {
    // Farmer trading at market instead of farm
    expect(resolveAgentLocation("farmer", true, action("trade_goods"))).toBe("market");
    // Soldier praying at church instead of green
    expect(resolveAgentLocation("soldier", true, action("pray"))).toBe("church");
  });

  it("sends dead agents to homes regardless of action or profession", () => {
    expect(resolveAgentLocation("soldier", false, action("patrol"))).toBe("homes");
    expect(resolveAgentLocation("merchant", false, undefined)).toBe("homes");
    expect(resolveAgentLocation("farmer", false, action("harvest_food"))).toBe("homes");
  });

  it("falls back to green for unknown profession with no action", () => {
    expect(resolveAgentLocation("unknown_profession", true, undefined)).toBe("green");
  });
});

// ---------------------------------------------------------------------------
// VillageMap rendering
// ---------------------------------------------------------------------------

describe("VillageMap rendering", () => {
  it("renders all seven building icons", () => {
    render(
      <VillageMap
        agents={[]}
        resolvedActions={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
      />,
    );
    for (const icon of ["🔨", "⛪", "🎪", "🏠", "🍺", "🌾", "🌿"]) {
      expect(screen.getByText(icon)).toBeTruthy();
    }
  });

  it("shows empty-state hint when no agents are provided", () => {
    render(
      <VillageMap
        agents={[]}
        resolvedActions={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
      />,
    );
    expect(screen.getByText("Advance a turn to place villagers")).toBeTruthy();
  });

  it("does not show empty-state hint when agents are present", () => {
    render(
      <VillageMap
        agents={[BASE_AGENT]}
        resolvedActions={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
      />,
    );
    expect(screen.queryByText("Advance a turn to place villagers")).toBeNull();
  });

  it("renders agent token on the map without initials text", () => {
    render(
      <VillageMap
        agents={[BASE_AGENT]}
        resolvedActions={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
      />,
    );
    expect(screen.getByTestId("agent-token-1")).toBeTruthy();
    expect(screen.queryByText("AL")).toBeNull();
  });

  it("calls onSelectAgent with the correct id when a token is clicked", () => {
    const onSelect = vi.fn();
    render(
      <VillageMap
        agents={[BASE_AGENT]}
        resolvedActions={null}
        selectedAgentId={null}
        onSelectAgent={onSelect}
      />,
    );
    fireEvent.click(screen.getByTestId("agent-token-1"));
    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("renders selection ring for the selected agent", () => {
    render(
      <VillageMap
        agents={[BASE_AGENT]}
        resolvedActions={null}
        selectedAgentId={1}
        onSelectAgent={vi.fn()}
      />,
    );
    expect(screen.getByTestId("agent-selected-1")).toBeTruthy();
  });

  it("does not render selection ring for an unselected agent", () => {
    render(
      <VillageMap
        agents={[BASE_AGENT]}
        resolvedActions={null}
        selectedAgentId={99}
        onSelectAgent={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("agent-selected-1")).toBeNull();
  });

  it("renders separate tokens for multiple agents", () => {
    const agents: AgentSummary[] = [
      { id: 1, name: "Aldric", profession: "farmer",   age: 30, is_alive: true, is_sick: false, hunger: 0 },
      { id: 2, name: "Elena",  profession: "merchant", age: 28, is_alive: true, is_sick: false, hunger: 0 },
    ];
    render(
      <VillageMap
        agents={agents}
        resolvedActions={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
      />,
    );
    expect(screen.getByTestId("agent-token-1")).toBeTruthy();
    expect(screen.getByTestId("agent-token-2")).toBeTruthy();
  });

  it("places agent at action-derived location, overriding profession default", () => {
    // Farmer with trade_goods → market (not farm)
    const fullAction: ResolvedAction = {
      agent_id: 1,
      action_type: "trade_goods",
      succeeded: true,
      outcome: "",
      details: {},
    };
    render(
      <VillageMap
        agents={[BASE_AGENT]}
        resolvedActions={[fullAction]}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
      />,
    );
    // Token exists — location derivation verified via resolveAgentLocation unit tests
    expect(screen.getByTestId("agent-token-1")).toBeTruthy();
    expect(resolveAgentLocation("farmer", true, fullAction)).toBe("market");
  });

  it("renders both tokens when two agents share the same building", () => {
    // Two farmers both default to farm — they should get separate slot positions
    const agents: AgentSummary[] = [
      { id: 1, name: "Aldric", profession: "farmer", age: 30, is_alive: true, is_sick: false, hunger: 0 },
      { id: 2, name: "Brenna", profession: "farmer", age: 25, is_alive: true, is_sick: false, hunger: 0 },
    ];
    render(
      <VillageMap
        agents={agents}
        resolvedActions={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
      />,
    );
    expect(screen.getByTestId("agent-token-1")).toBeTruthy();
    expect(screen.getByTestId("agent-token-2")).toBeTruthy();
  });

  it("renders deceased agents with reduced opacity token", () => {
    const deadAgent = { ...BASE_AGENT, is_alive: false };
    render(
      <VillageMap
        agents={[deadAgent]}
        resolvedActions={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
      />,
    );
    const token = screen.getByTestId("agent-token-1");
    // Dead agents get opacity:0.3 via inline style — check attribute string
    expect(token.getAttribute("style")).toContain("opacity: 0.3");
  });
});
