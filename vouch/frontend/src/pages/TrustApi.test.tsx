import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TrustApi } from "./TrustApi";
import { api } from "../api";

vi.mock("../api", () => ({
  ApiError: class ApiError extends Error {},
  api: {
    verify: vi.fn().mockResolvedValue({
      status: 200,
      data: {
        decision: "fail",
        confirmed: false,
        confidence: 40,
        brief: "'price' matches the distribution of 'shipping'.",
        failures: [
          { code: "COLUMN_SWAP", severity: "critical", field: "price", message: "swapped", evidence: {} },
        ],
        judge_consulted: false,
      },
    }),
  },
}));

const verify = vi.mocked(api.verify);

describe("TrustApi", () => {
  it("calls verify() with candidate + baseline records and renders the decision and failures", async () => {
    render(<TrustApi />);
    await waitFor(() => expect(verify).toHaveBeenCalled());
    const arg = verify.mock.calls[0][0];
    expect(Array.isArray(arg.candidate_records)).toBe(true);
    expect(arg.candidate_records.length).toBeGreaterThan(0);
    expect(Array.isArray(arg.baseline_records)).toBe(true);

    expect((await screen.findAllByText(/COLUMN_SWAP/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("img", { name: /fail/i })).toBeInTheDocument();
    // the real HTTP status is shown, not a hardcoded literal
    expect(screen.getByText("200")).toBeInTheDocument();
  });

  it("loads a preset without running, then runs on the button click", async () => {
    render(<TrustApi />);
    await waitFor(() => expect(verify).toHaveBeenCalled()); // auto-run once on mount
    verify.mockClear();

    // Selecting a preset must NOT run — it only loads the request JSON.
    await userEvent.click(screen.getByRole("button", { name: /clean heal/i }));
    expect(verify).not.toHaveBeenCalled();

    // The button is what runs it.
    await userEvent.click(screen.getByRole("button", { name: /run through the guardian/i }));
    await waitFor(() => expect(verify).toHaveBeenCalled());
    const arg = verify.mock.calls.at(-1)![0];
    expect(Array.isArray(arg.candidate_records)).toBe(true);
    expect(Array.isArray(arg.baseline_records)).toBe(true);
  });
});
