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
      status: 200,
      data: {
        decision: "fail",
        confirmed: false,
        confidence: 40,
        brief: "x",
        failures: [],
        judge_consulted: false,
      },
    }),
  },
}));

describe("routing", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  // The DemoMenu control's exact accessible name, so probes for it never collide with the hero's
  // "repricer demo" navigation buttons.
  const DEMO_CONTROL = /demo — simulate/i;

  it("shows the hero at the root and switches views via nav", async () => {
    render(<App />);
    // Hero (kicker is a single text node; the headline is split across a span)
    expect(await screen.findByText(/the trust layer for scraped data/i)).toBeInTheDocument();
    expect(screen.getByText(/never act on a number/i)).toBeInTheDocument();

    // Into the repricer demo (console)
    await userEvent.click(screen.getAllByRole("button", { name: /repricer demo/i })[0]);
    expect((await screen.findAllByText(/needs your decision|pricing desk/i)).length).toBeGreaterThan(0);

    // Over to the Trust API (the hero's product)
    await userEvent.click(screen.getByRole("button", { name: /^trust api$/i }));
    expect(await screen.findByText(/run through the guardian/i)).toBeInTheDocument();

    // Back to the repricer tab
    await userEvent.click(screen.getByRole("button", { name: /^repricer$/i }));
    expect((await screen.findAllByText(/pricing desk|needs your decision/i)).length).toBeGreaterThan(0);
  });

  it("scopes the Demo control to the Console route only", async () => {
    render(<App />);

    // Not on the Hero.
    expect(await screen.findByText(/the trust layer for scraped data/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: DEMO_CONTROL })).not.toBeInTheDocument();

    // Present on the Console.
    await userEvent.click(screen.getAllByRole("button", { name: /repricer demo/i })[0]);
    expect(await screen.findByRole("button", { name: DEMO_CONTROL })).toBeInTheDocument();

    // Gone again on the Trust API.
    await userEvent.click(screen.getByRole("button", { name: /^trust api$/i }));
    expect(await screen.findByText(/run through the guardian/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: DEMO_CONTROL })).not.toBeInTheDocument();
  });
});
