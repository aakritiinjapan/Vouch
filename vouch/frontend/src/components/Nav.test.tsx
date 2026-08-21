import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { Nav } from "./Nav";

describe("Nav", () => {
  it("hides the tenant label below sm to avoid mobile horizontal scroll", () => {
    render(<Nav view="console" navigate={vi.fn()} />);
    const label = screen.getByTestId("tenant-label");
    expect(label).toHaveClass("hidden");
    expect(label).toHaveClass("sm:inline");
  });

  it("marks the active tab", () => {
    render(<Nav view="trust-api" navigate={vi.fn()} />);
    expect(screen.getByRole("button", { name: /^trust api$/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});
