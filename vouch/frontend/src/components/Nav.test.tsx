import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Nav } from "./Nav";
import type { DemoHint } from "../types";

const HINTS: DemoHint[] = [
  { key: "healed_swapped", label: "Replay: shipping swap", detail: "swap detail", stage: "heal" },
];

function demoProps() {
  return {
    hints: HINTS,
    busy: null as string | null,
    onRunCycle: vi.fn(),
    onReplay: vi.fn(),
    onResume: vi.fn(),
    onReset: vi.fn(),
  };
}

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

  it("renders the Demo control only when demo handlers are provided", () => {
    const { rerender } = render(<Nav view="console" navigate={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /demo/i })).not.toBeInTheDocument();

    rerender(<Nav view="console" navigate={vi.fn()} demo={demoProps()} />);
    const trigger = screen.getByRole("button", { name: /demo/i });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});

describe("Demo control", () => {
  it("opens a menu with the expected items on click", async () => {
    render(<Nav view="console" navigate={vi.fn()} demo={demoProps()} />);
    const trigger = screen.getByRole("button", { name: /demo/i });

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await userEvent.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menu")).toBeInTheDocument();
    const items = screen.getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual([
      expect.stringMatching(/check competitors now/i),
      expect.stringMatching(/replay: shipping swap/i),
      expect.stringMatching(/re-prompt & resume/i),
      expect.stringMatching(/reset demo/i),
    ]);
  });

  it("links both worked examples when a handler is supplied, after the simulation actions", async () => {
    const onOpenExample = vi.fn();
    render(
      <Nav view="console" navigate={vi.fn()} demo={{ ...demoProps(), onOpenExample }} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /demo/i }));

    const labels = screen.getAllByRole("menuitem").map((i) => i.textContent ?? "");
    expect(labels.at(-2)).toMatch(/example ①: competitive repricing/i);
    expect(labels.at(-1)).toMatch(/example ②: sale price audit/i);

    await userEvent.click(screen.getByRole("menuitem", { name: /sale price audit/i }));
    expect(onOpenExample).toHaveBeenCalledWith("sale-audit");
  });

  it("omits the example links when no handler is supplied", async () => {
    render(<Nav view="console" navigate={vi.fn()} demo={demoProps()} />);
    await userEvent.click(screen.getByRole("button", { name: /demo/i }));
    expect(screen.queryByRole("menuitem", { name: /example ①/i })).not.toBeInTheDocument();
  });

  it("exposes the strip caption as a tooltip", () => {
    render(<Nav view="console" navigate={vi.fn()} demo={demoProps()} />);
    expect(screen.getByRole("tooltip")).toHaveTextContent(/simulate real scraping events/i);
  });

  it("calls the matching handler and closes when an item is selected", async () => {
    const demo = demoProps();
    render(<Nav view="console" navigate={vi.fn()} demo={demo} />);
    await userEvent.click(screen.getByRole("button", { name: /demo/i }));

    await userEvent.click(screen.getByRole("menuitem", { name: /replay: shipping swap/i }));
    expect(demo.onReplay).toHaveBeenCalledWith("healed_swapped");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("wires the primary and utility actions", async () => {
    const demo = demoProps();
    render(<Nav view="console" navigate={vi.fn()} demo={demo} />);

    await userEvent.click(screen.getByRole("button", { name: /demo/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /check competitors now/i }));
    expect(demo.onRunCycle).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: /demo/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /re-prompt & resume/i }));
    expect(demo.onResume).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: /demo/i }));
    await userEvent.click(screen.getByRole("menuitem", { name: /reset demo/i }));
    expect(demo.onReset).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    render(<Nav view="console" navigate={vi.fn()} demo={demoProps()} />);
    const trigger = screen.getByRole("button", { name: /demo/i });
    await userEvent.click(trigger);
    expect(screen.getByRole("menu")).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("closes on an outside click", async () => {
    render(
      <div>
        <Nav view="console" navigate={vi.fn()} demo={demoProps()} />
        <button type="button">outside</button>
      </div>,
    );
    await userEvent.click(screen.getByRole("button", { name: /demo/i }));
    expect(screen.getByRole("menu")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /outside/i }));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
