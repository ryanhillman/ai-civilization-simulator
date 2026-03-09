/**
 * Ask-agent UI tests.
 *
 * Tests the AskAgentSection component (embedded in AgentPanel) using
 * mocked API calls — no live backend needed.
 *
 * Covers:
 *  - Input renders and accepts text
 *  - Submit button is disabled when input is empty
 *  - Submit button becomes enabled after typing
 *  - Calls aiApi.askAgent with correct args on submit
 *  - Displays the answer after a successful response
 *  - Shows fallback note when fallback=true in response
 *  - Shows error message when API call fails
 *  - Enter key triggers submission
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AgentPanel from "../AgentPanel";
import * as client from "@/api/client";
import type { AgentDetail, AskAgentResponse } from "@/types";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/api/client", () => ({
  agentApi: {
    get: vi.fn(),
  },
  aiApi: {
    askAgent: vi.fn(),
  },
}));

const mockAgentApi = client.agentApi as { get: ReturnType<typeof vi.fn> };
const mockAiApi = client.aiApi as { askAgent: ReturnType<typeof vi.fn> };

function makeAgent(overrides: Partial<AgentDetail> = {}): AgentDetail {
  return {
    id: 1,
    name: "Aldric",
    profession: "farmer",
    age: 42,
    is_alive: true,
    is_sick: false,
    hunger: 0.2,
    personality_traits: { courage: 0.4, greed: 0.2, warmth: 0.8, cunning: 0.2, piety: 0.5 },
    goals: [{ type: "produce", target: "food", priority: 1 }],
    inventory: { food: 18, coin: 5, wood: 8, medicine: 1 },
    relationships: [],
    recent_memories: [],
    ...overrides,
  };
}

function wrapper(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      {ui}
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AskAgentSection (inside AgentPanel)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAgentApi.get.mockResolvedValue(makeAgent());
  });

  it("renders ask input and button", async () => {
    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => expect(screen.getByPlaceholderText(/ask a question/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /ask/i })).toBeInTheDocument();
  });

  it("submit button is disabled when input is empty", async () => {
    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));
    const btn = screen.getByRole("button", { name: /ask/i });
    expect(btn).toBeDisabled();
  });

  it("submit button enables after typing a question", async () => {
    const user = userEvent.setup();
    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    await user.type(screen.getByPlaceholderText(/ask a question/i), "What do you grow?");
    expect(screen.getByRole("button", { name: /ask/i })).not.toBeDisabled();
  });

  it("calls aiApi.askAgent with correct args on submit", async () => {
    const user = userEvent.setup();
    const mockResp: AskAgentResponse = {
      agent_id: 1,
      agent_name: "Aldric",
      answer: "I grow wheat and barley.",
      ai_enabled: true,
      fallback: false,
    };
    mockAiApi.askAgent.mockResolvedValueOnce(mockResp);

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    await user.type(screen.getByPlaceholderText(/ask a question/i), "What do you grow?");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    expect(mockAiApi.askAgent).toHaveBeenCalledWith(1, 1, "What do you grow?");
  });

  it("displays the answer after successful response", async () => {
    const user = userEvent.setup();
    const mockResp: AskAgentResponse = {
      agent_id: 1,
      agent_name: "Aldric",
      answer: "I grow wheat and barley.",
      ai_enabled: true,
      fallback: false,
    };
    mockAiApi.askAgent.mockResolvedValueOnce(mockResp);

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    await user.type(screen.getByPlaceholderText(/ask a question/i), "Crops?");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    await waitFor(() =>
      expect(screen.getByText(/I grow wheat and barley/i)).toBeInTheDocument()
    );
  });

  it("shows fallback note when fallback=true", async () => {
    const user = userEvent.setup();
    mockAiApi.askAgent.mockResolvedValueOnce({
      agent_id: 1,
      agent_name: "Aldric",
      answer: "I cannot speak now.",
      ai_enabled: false,
      fallback: true,
    } satisfies AskAgentResponse);

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    await user.type(screen.getByPlaceholderText(/ask a question/i), "Hello?");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    await waitFor(() =>
      expect(screen.getByText(/AI unavailable/i)).toBeInTheDocument()
    );
  });

  it("shows error message on API failure", async () => {
    const user = userEvent.setup();
    mockAiApi.askAgent.mockRejectedValueOnce(new Error("network error"));

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    await user.type(screen.getByPlaceholderText(/ask a question/i), "Hello?");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    await waitFor(() =>
      expect(screen.getByText(/could not reach/i)).toBeInTheDocument()
    );
  });

  it("clears input after successful submission", async () => {
    const user = userEvent.setup();
    mockAiApi.askAgent.mockResolvedValueOnce({
      agent_id: 1, agent_name: "Aldric",
      answer: "Good morrow.", ai_enabled: true, fallback: false,
    } satisfies AskAgentResponse);

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    const input = screen.getByPlaceholderText(/ask a question/i);
    await user.type(input, "Morning?");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    await waitFor(() => expect((input as HTMLInputElement).value).toBe(""));
  });

  // -------------------------------------------------------------------------
  // Consecutive question handling (regression for stale-answer bug)
  // -------------------------------------------------------------------------

  it("previous answer clears immediately when second question is submitted", async () => {
    const user = userEvent.setup();

    // First answer resolves right away
    mockAiApi.askAgent.mockResolvedValueOnce({
      agent_id: 1, agent_name: "Aldric",
      answer: "First answer text.", ai_enabled: true, fallback: false,
    } satisfies AskAgentResponse);

    // Second answer is deferred so we can inspect mid-flight state
    let resolveSecond!: (v: AskAgentResponse) => void;
    mockAiApi.askAgent.mockReturnValueOnce(
      new Promise<AskAgentResponse>((res) => { resolveSecond = res; })
    );

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    // First submission
    await user.type(screen.getByPlaceholderText(/ask a question/i), "First question?");
    await user.click(screen.getByRole("button", { name: /ask/i }));
    await waitFor(() => expect(screen.getByText(/First answer text/i)).toBeInTheDocument());

    // Second submission — stale answer must disappear before the response arrives
    await user.type(screen.getByPlaceholderText(/ask a question/i), "Second question?");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    await waitFor(() =>
      expect(screen.queryByText(/First answer text/i)).not.toBeInTheDocument()
    );

    // Resolve the second request
    resolveSecond({
      agent_id: 1, agent_name: "Aldric",
      answer: "Second answer text.", ai_enabled: true, fallback: false,
    });
    await waitFor(() =>
      expect(screen.getByText(/Second answer text/i)).toBeInTheDocument()
    );
  });

  it("second answer replaces first answer after both resolve", async () => {
    const user = userEvent.setup();

    mockAiApi.askAgent
      .mockResolvedValueOnce({
        agent_id: 1, agent_name: "Aldric",
        answer: "Answer one.", ai_enabled: true, fallback: false,
      } satisfies AskAgentResponse)
      .mockResolvedValueOnce({
        agent_id: 1, agent_name: "Aldric",
        answer: "Answer two.", ai_enabled: true, fallback: false,
      } satisfies AskAgentResponse);

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    // First round
    await user.type(screen.getByPlaceholderText(/ask a question/i), "Q1?");
    await user.click(screen.getByRole("button", { name: /ask/i }));
    await waitFor(() => expect(screen.getByText(/Answer one/i)).toBeInTheDocument());

    // Second round
    await user.type(screen.getByPlaceholderText(/ask a question/i), "Q2?");
    await user.click(screen.getByRole("button", { name: /ask/i }));
    await waitFor(() => expect(screen.getByText(/Answer two/i)).toBeInTheDocument());

    // First answer must be gone
    expect(screen.queryByText(/Answer one/i)).not.toBeInTheDocument();
  });

  it("button shows loading indicator during second in-flight request", async () => {
    const user = userEvent.setup();

    // First resolves immediately
    mockAiApi.askAgent.mockResolvedValueOnce({
      agent_id: 1, agent_name: "Aldric",
      answer: "Initial.", ai_enabled: true, fallback: false,
    } satisfies AskAgentResponse);

    // Second is deferred
    let resolveSecond!: (v: AskAgentResponse) => void;
    mockAiApi.askAgent.mockReturnValueOnce(
      new Promise<AskAgentResponse>((res) => { resolveSecond = res; })
    );

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    await user.type(screen.getByPlaceholderText(/ask a question/i), "Q1?");
    await user.click(screen.getByRole("button", { name: /ask/i }));
    await waitFor(() => expect(screen.getByText(/Initial/i)).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText(/ask a question/i), "Q2?");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    // Button should show pending indicator and be disabled while in flight
    await waitFor(() => expect(screen.getByRole("button", { name: /\.\.\./i })).toBeDisabled());

    resolveSecond({
      agent_id: 1, agent_name: "Aldric",
      answer: "Done.", ai_enabled: true, fallback: false,
    });
    await waitFor(() => expect(screen.getByText(/Done/i)).toBeInTheDocument());
  });

  it("error state clears on retry and shows new answer", async () => {
    const user = userEvent.setup();

    // First call fails
    mockAiApi.askAgent.mockRejectedValueOnce(new Error("timeout"));
    // Second call succeeds
    mockAiApi.askAgent.mockResolvedValueOnce({
      agent_id: 1, agent_name: "Aldric",
      answer: "Retry success.", ai_enabled: true, fallback: false,
    } satisfies AskAgentResponse);

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByPlaceholderText(/ask a question/i));

    // First attempt — fails
    await user.type(screen.getByPlaceholderText(/ask a question/i), "Q1?");
    await user.click(screen.getByRole("button", { name: /ask/i }));
    await waitFor(() => expect(screen.getByText(/could not reach/i)).toBeInTheDocument());

    // Retry with a new question
    await user.type(screen.getByPlaceholderText(/ask a question/i), " retry");
    await user.click(screen.getByRole("button", { name: /ask/i }));

    await waitFor(() => expect(screen.getByText(/Retry success/i)).toBeInTheDocument());
    expect(screen.queryByText(/could not reach/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Dead-agent "Recall" consecutive question handling
// ---------------------------------------------------------------------------

describe("AskAgentSection — dead agent (Recall flow)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAgentApi.get.mockResolvedValue(makeAgent({ is_alive: false }));
  });

  it("renders Recall button for deceased agent", async () => {
    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => expect(screen.getByRole("button", { name: /recall/i })).toBeInTheDocument());
  });

  it("previous chronicle entry clears when Recall is pressed again", async () => {
    const user = userEvent.setup();

    mockAiApi.askAgent.mockResolvedValueOnce({
      agent_id: 1, agent_name: "Aldric",
      answer: "First chronicle entry.", ai_enabled: false, fallback: true, agent_deceased: true,
    } satisfies AskAgentResponse);

    let resolveSecond!: (v: AskAgentResponse) => void;
    mockAiApi.askAgent.mockReturnValueOnce(
      new Promise<AskAgentResponse>((res) => { resolveSecond = res; })
    );

    render(wrapper(<AgentPanel worldId={1} agentId={1} lastResult={null} />));
    await waitFor(() => screen.getByRole("button", { name: /recall/i }));

    // First recall
    await user.type(screen.getByPlaceholderText(/ask about/i), "What was their story?");
    await user.click(screen.getByRole("button", { name: /recall/i }));
    await waitFor(() => expect(screen.getByText(/First chronicle entry/i)).toBeInTheDocument());

    // Second recall — stale chronicle text must clear immediately
    await user.type(screen.getByPlaceholderText(/ask about/i), " again");
    await user.click(screen.getByRole("button", { name: /recall/i }));

    await waitFor(() =>
      expect(screen.queryByText(/First chronicle entry/i)).not.toBeInTheDocument()
    );

    // Resolve second request
    resolveSecond({
      agent_id: 1, agent_name: "Aldric",
      answer: "Second chronicle entry.", ai_enabled: false, fallback: true, agent_deceased: true,
    });
    await waitFor(() =>
      expect(screen.getByText(/Second chronicle entry/i)).toBeInTheDocument()
    );
  });
});
