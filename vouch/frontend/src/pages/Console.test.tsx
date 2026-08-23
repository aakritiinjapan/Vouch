import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Console } from "./Console";
import { makeGuardian, makeHealEvent, makeHeld, makePending, makeProduct } from "../test/fixtures";

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
    onApprove: vi.fn(),
    onReject: vi.fn(),
    onApproveAllSafe: vi.fn(),
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

  it("renders every hold collapsed by default and expands one in place on click", async () => {
    const held = [
      makeHeld({ id: 101, guardian: makeGuardian({ heal_event_id: 10 }) }),
      makeHeld({ id: 102, guardian: makeGuardian({ heal_event_id: 11 }) }),
    ];
    const { container } = render(<Console {...baseProps()} held={held} />);

    // Nothing is expanded on initial load: the "Reprice on hold" heading only exists when expanded.
    expect(screen.queryAllByText(/reprice on hold/i)).toHaveLength(0);
    const collapsedToggles = screen.getAllByRole("button", { name: /expand this decision/i });
    expect(collapsedToggles).toHaveLength(2);

    // Clicking one expands it in place, and only it — the other stays collapsed.
    await userEvent.click(collapsedToggles[0]);
    expect(screen.getAllByText(/reprice on hold/i)).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /expand this decision/i })).toHaveLength(1);
  });

  it("cross-links a hold to its matching receipt on hover, and back", () => {
    const held = [makeHeld({ id: 101, guardian: makeGuardian({ heal_event_id: 10 }) })];
    const events = [makeHealEvent({ id: 10 })];
    const { container } = render(<Console {...baseProps()} held={held} healEvents={events} />);

    const holdEl = container.querySelector('article[data-link-id="10"]') as HTMLElement;
    const receiptEl = container.querySelector('li[data-link-id="10"]') as HTMLElement;
    expect(holdEl).toBeTruthy();
    expect(receiptEl).toBeTruthy();

    // Idle: neither is highlighted.
    expect(holdEl.className).not.toMatch(/ring-brand/);
    expect(receiptEl.className).not.toMatch(/ring-brand/);

    // Hovering the hold highlights the matching receipt.
    fireEvent.mouseEnter(holdEl);
    expect(receiptEl.className).toMatch(/ring-brand/);
    fireEvent.mouseLeave(holdEl);
    expect(receiptEl.className).not.toMatch(/ring-brand/);

    // Hovering the receipt highlights the matching hold (bidirectional).
    fireEvent.mouseEnter(receiptEl);
    expect(holdEl.className).toMatch(/ring-brand/);
    fireEvent.mouseLeave(receiptEl);
    expect(holdEl.className).not.toMatch(/ring-brand/);

    // Keyboard focus works the same way.
    fireEvent.focus(receiptEl);
    expect(holdEl.className).toMatch(/ring-brand/);
    fireEvent.blur(receiptEl);
    expect(holdEl.className).not.toMatch(/ring-brand/);
  });
});
