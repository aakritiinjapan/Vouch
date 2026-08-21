import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App";

vi.mock("./api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    products: vi.fn().mockResolvedValue([]),
    proposals: vi.fn().mockResolvedValue([]),
    healEvents: vi.fn().mockResolvedValue([]),
    demoHints: vi.fn().mockResolvedValue({
      mock_mode: true,
      dataset: "gpu",
      dataset_note: "8 GPUs from Newegg",
      hints: [],
    }),
    history: vi.fn().mockResolvedValue({ points: [], counterfactual: null }),
    verify: vi.fn().mockResolvedValue({
      decision: "fail",
      confirmed: false,
      confidence: 40,
      brief: "x",
      failures: [],
      judge_consulted: false,
    }),
  },
}));

describe("routing", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  it("shows the hero at the root and switches views via nav", async () => {
    render(<App />);
    // Hero (kicker is a single text node; the headline is split across a span)
    expect(await screen.findByText(/the trust layer for scraped data/i)).toBeInTheDocument();
    expect(screen.getByText(/never act on a number/i)).toBeInTheDocument();

    // Into the console
    await userEvent.click(screen.getAllByRole("button", { name: /launch console/i })[0]);
    expect((await screen.findAllByText(/needs your decision|pricing desk/i)).length).toBeGreaterThan(0);

    // Over to the Trust API
    await userEvent.click(screen.getByRole("button", { name: /^trust api$/i }));
    expect(await screen.findByText(/run through the guardian/i)).toBeInTheDocument();

    // Back to the console
    await userEvent.click(screen.getByRole("button", { name: /^console$/i }));
    expect((await screen.findAllByText(/pricing desk|needs your decision/i)).length).toBeGreaterThan(0);
  });
});
