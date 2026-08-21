import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { Console } from "./Console";
import { makeHealEvent, makeHeld, makePending, makeProduct } from "../test/fixtures";

vi.mock("../api", () => ({
  api: { history: vi.fn().mockResolvedValue({ points: [], counterfactual: null }) },
}));

function baseProps() {
  return {
    products: [makeProduct()],
    pending: [makePending()],
    held: [] as ReturnType<typeof makeHeld>[],
    healEvents: [makeHealEvent()],
    loading: false,
    busy: null as string | null,
    mockMode: true,
    hints: [],
    datasetNote: "8 GPUs",
    collectorId: "gd_collector_abc",
    onApprove: vi.fn(),
    onReject: vi.fn(),
    onApproveAllSafe: vi.fn(),
    onRunCycle: vi.fn(),
    onReplay: vi.fn(),
    onResume: vi.fn(),
    onReset: vi.fn(),
    onViewAsApi: vi.fn(),
  };
}

describe("Console", () => {
  it("renders the held section above the routine list when something is held", () => {
    render(<Console {...baseProps()} held={[makeHeld()]} />);
    const decision = screen.getByText(/needs your decision/i);
    const ready = screen.getByText(/ready to apply/i);
    expect(decision.compareDocumentPosition(ready) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders empty states when nothing is held and nothing is routine", () => {
    render(<Console {...baseProps()} held={[]} pending={[]} />);
    expect(
      screen.getAllByText(/nothing.*hold|every source|all sources|nothing needs|nothing routine/i)
        .length,
    ).toBeGreaterThan(0);
  });

  it("renders trust-metric tiles with values", () => {
    render(<Console {...baseProps()} held={[makeHeld()]} />);
    expect(screen.getByText(/margin protected/i)).toBeInTheDocument();
    expect(screen.getByText(/bad reprices caught/i)).toBeInTheDocument();
    // the margin-protected figure (abs profit delta of the held card)
    expect(screen.getAllByText(/\$179/).length).toBeGreaterThan(0);
  });

  it("shows the vs-Newegg scope line", () => {
    render(<Console {...baseProps()} />);
    expect(screen.getAllByText(/newegg/i).length).toBeGreaterThan(0);
  });
});
