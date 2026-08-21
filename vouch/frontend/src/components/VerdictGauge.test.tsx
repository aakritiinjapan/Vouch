import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { VerdictChip, VerdictGauge } from "./VerdictGauge";

describe("VerdictGauge", () => {
  it("renders the score and a PASS state with an accessible label", () => {
    render(<VerdictGauge decision="pass" score={100} />);
    const gauge = screen.getByRole("img", { name: /pass/i });
    expect(gauge).toHaveAttribute("aria-label", expect.stringContaining("100"));
    expect(gauge).toHaveAttribute("aria-label", expect.stringMatching(/high/i));
    expect(screen.getByText("100")).toBeInTheDocument();
  });

  it("renders a FAIL state reflecting decision and score", () => {
    render(<VerdictGauge decision="fail" score={40} />);
    const gauge = screen.getByRole("img", { name: /fail/i });
    expect(gauge.getAttribute("aria-label")).toMatch(/40/);
    expect(gauge.getAttribute("aria-label")).toMatch(/low/i);
    expect(screen.getByText("40")).toBeInTheDocument();
  });

  it("drops the ticks and glyph at small (chip/receipt) sizes but keeps the score and a11y label", () => {
    render(<VerdictGauge decision="fail" score={40} size={54} />);
    // score stays
    expect(screen.getByText("40")).toBeInTheDocument();
    // the inner FAIL glyph is dropped at compact size
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
