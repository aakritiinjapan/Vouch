import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Receipts } from "./Receipts";
import { makeHealEvent } from "../test/fixtures";

describe("Receipts", () => {
  it("renders each receipt collapsed to a terse one-line verdict, and toggles open/closed", async () => {
    render(<Receipts events={[makeHealEvent()]} />);

    // Collapsed: the terse verdict line is shown; the numbered steps are hidden.
    expect(screen.getByText(/FAIL · COLUMN_SWAP · 40\/100/)).toBeInTheDocument();
    expect(screen.queryByText(/scraper auto-fixed itself/i)).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /msi rtx 5080/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    // Expand → the steps appear.
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/scraper auto-fixed itself/i)).toBeInTheDocument();

    // Collapse again → hidden.
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/scraper auto-fixed itself/i)).not.toBeInTheDocument();
  });

  it("highlights the receipt whose id matches the active link id", () => {
    const { container } = render(
      <Receipts events={[makeHealEvent({ id: 10 })]} activeLinkId={10} onLinkActivate={vi.fn()} />,
    );
    const row = container.querySelector('li[data-link-id="10"]') as HTMLElement;
    expect(row.className).toMatch(/ring-brand/);
  });
});
