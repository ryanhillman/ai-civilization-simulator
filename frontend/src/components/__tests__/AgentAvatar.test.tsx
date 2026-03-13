import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentAvatar } from "../AgentAvatar";

describe("AgentAvatar", () => {
  it("renders a face ellipse as the portrait", () => {
    const { container } = render(<AgentAvatar id={1} name="Edmund" />);
    // The face is an <ellipse> — verify it exists (portrait is sole visual identifier)
    const ellipses = container.querySelectorAll("ellipse");
    expect(ellipses.length).toBeGreaterThan(0);
  });

  it("does not render initials text (portrait is the sole identifier)", () => {
    const { container } = render(<AgentAvatar id={1} name="Edmund" />);
    expect(container.querySelector("text")).toBeNull();
  });

  it("renders at default size 32", () => {
    const { container } = render(<AgentAvatar id={1} name="Edmund" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "32");
    expect(svg).toHaveAttribute("height", "32");
  });

  it("renders at custom size", () => {
    const { container } = render(<AgentAvatar id={1} name="Edmund" size={48} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "48");
    expect(svg).toHaveAttribute("height", "48");
  });

  it("does not show sick indicator when isSick is false", () => {
    render(<AgentAvatar id={1} name="Edmund" isSick={false} />);
    expect(screen.queryByLabelText("sick indicator")).toBeNull();
  });

  it("shows sick indicator when isSick is true", () => {
    render(<AgentAvatar id={1} name="Edmund" isSick={true} />);
    expect(screen.getByLabelText("sick indicator")).toBeTruthy();
  });

  it("uses different palette colors for different IDs (deterministic)", () => {
    // IDs 0 and 8 share the same palette slot (8 % 8 === 0)
    const { container: c0 } = render(<AgentAvatar id={0} name="A" />);
    const { container: c8 } = render(<AgentAvatar id={8} name="A" />);
    const fill0 = c0.querySelector("circle")?.getAttribute("fill");
    const fill8 = c8.querySelector("circle")?.getAttribute("fill");
    expect(fill0).toBe(fill8);

    // IDs 0 and 1 should differ
    const { container: c1 } = render(<AgentAvatar id={1} name="A" />);
    const fill1 = c1.querySelector("circle")?.getAttribute("fill");
    expect(fill0).not.toBe(fill1);
  });

  it("has aria-label with agent name", () => {
    const { container } = render(<AgentAvatar id={3} name="Theodora" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-label", "Theodora avatar");
  });
});
