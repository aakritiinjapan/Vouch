import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { VerdictChip, VerdictSeal } from "./VerdictSeal";

describe("VerdictSeal", () => {
  it("renders the score and a PASS state with an accessible label", () => {
    render(<VerdictSeal decision="pass" score={100} />);
    const seal = screen.getByRole("img", { name: /pass/i });
    expect(seal).toHaveAttribute("aria-label", expect.stringContaining("100"));
    expect(seal).toHaveAttribute("aria-label", expect.stringMatching(/high/i));
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  it("renders a FAIL state reflecting decision and score", () => {
    render(<VerdictSeal decision="fail" score={40} />);
    const seal = screen.getByRole("img", { name: /fail/i });
    expect(seal.getAttribute("aria-label")).toMatch(/40/);
    expect(seal.getAttribute("aria-label")).toMatch(/low/i);
    expect(screen.getByText("40")).toBeInTheDocument();
  });

  it("hides the illegible microtext at small (chip/receipt) sizes but keeps the score and label", () => {
    render(<VerdictSeal decision="fail" score={40} size={54} />);
    // score glyph stays
    expect(screen.getByText("40")).toBeInTheDocument();
    // the inner FAIL/band microtext is dropped
    expect(screen.queryByText("FAIL")).not.toBeInTheDocument();
    // but the decision is still announced accessibly
    expect(screen.getByRole("img", { name: /fail/i })).toBeInTheDocument();
  });
});

describe("VerdictChip", () => {
  it("fires the view-as-API bridge when provided", async () => {
    const onView = vi.fn();
    render(
      <VerdictChip decision="fail" score={40} line="read shipping as the price" onViewAsApi={onView} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /view as api/i }));
    expect(onView).toHaveBeenCalledOnce();
  });
});
