import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { HeldCard } from "./HeldCard";
import { makeHeld } from "../test/fixtures";

vi.mock("../api", () => ({
  api: { history: vi.fn().mockResolvedValue({ points: [], counterfactual: null }) },
}));

describe("HeldCard", () => {
  it("leads with the price facts, competitor status, plain-English reason, and the seal", () => {
    render(
      <HeldCard proposal={makeHeld()} busy={null} onApproveAnyway={vi.fn()} onSkip={vi.fn()} />,
    );
    // our price / margin
    expect(screen.getByText(/\$1,279\.99/)).toBeInTheDocument();
    expect(screen.getByText(/22\.0%/)).toBeInTheDocument();
    // competitor could not be verified
    expect(screen.getAllByText(/couldn.t verify|unconfirmed/i).length).toBeGreaterThan(0);
    // plain-English reason from the COLUMN_SWAP evidence
    expect(screen.getByText(/SHIPPING/)).toBeInTheDocument();
    // the seal
    expect(screen.getByRole("img", { name: /fail/i })).toBeInTheDocument();
  });

  it("calls onApproveAnyway through the confirm step and onSkip directly", async () => {
    const onApprove = vi.fn();
    const onSkip = vi.fn();
    render(
      <HeldCard proposal={makeHeld()} busy={null} onApproveAnyway={onApprove} onSkip={onSkip} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /approve anyway/i }));
    await userEvent.click(screen.getByRole("button", { name: /yes, approve/i }));
    expect(onApprove).toHaveBeenCalledWith(101);

    await userEvent.click(screen.getByRole("button", { name: /skip/i }));
    expect(onSkip).toHaveBeenCalledWith(101);
  });

  it("bridges to the Trust API via view-as-API", async () => {
    const onView = vi.fn();
    render(
      <HeldCard
        proposal={makeHeld()}
        busy={null}
        onApproveAnyway={vi.fn()}
        onSkip={vi.fn()}
        onViewAsApi={onView}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /view as api/i }));
    expect(onView).toHaveBeenCalledOnce();
  });
});
