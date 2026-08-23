/**
 * The console now serves two pipelines from one screen, which is the whole architectural claim:
 * if the verification layer is the product, a second consumer must not need a second console.
 *
 * So these tests care mostly about the seam - that switching the scenario really re-asks the
 * guardian rather than re-labelling the same rows, and that the sale audit renders numbers the
 * ENDPOINT returned rather than numbers the fixture happens to contain.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Console } from "./Console";
import { makeGuardian, makeHealEvent, makeHeld, makePending, makeProduct } from "../test/fixtures";

const verify = vi.fn();

vi.mock("../api", () => ({
  api: {
    history: vi.fn().mockResolvedValue({ points: [], counterfactual: null }),
    verify: (...args: unknown[]) => verify(...args),
  },
}));

/** One aggregated REFERENCE_PRICE_UNSUPPORTED result, shaped exactly as the backend returns it. */
function saleResponse() {
  return {
    status: 200,
    data: {
      decision: "pass",
      confirmed: true,
      confidence: 97,
      brief: "2 of 2 products advertise a was-price higher than anything we recorded.",
      judge_consulted: false,
      failures: [
        {
          code: "REFERENCE_PRICE_UNSUPPORTED",
          severity: "low",
          field: "original_price",
          message: "2 of 2 products advertise a was-price higher than our record.",
          evidence: {
            products_affected: 2,
            products_checked: 2,
            examples: [
              {
                product: "Voltmart RTX 5090 Titan Liquid 32GB",
                claimed_original: 3919.98,
                confirmed_before_sale: 2449.99,
                overstated_by: 1469.99,
                current_price: 1714.99,
              },
              {
                product: "Voltmart RTX 4080 Super Ventus 16GB",
                claimed_original: 1599.98,
                confirmed_before_sale: 999.99,
                overstated_by: 599.99,
                current_price: 699.99,
              },
            ],
          },
        },
      ],
    },
  };
}

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

async function switchToSaleAudit() {
  await userEvent.selectOptions(screen.getByRole("combobox"), "sale-audit");
}

describe("Console", () => {
  beforeEach(() => {
    verify.mockReset();
    verify.mockResolvedValue(saleResponse());
  });

  it("lists one row per held decision, with its finding code", () => {
    render(<Console {...baseProps()} held={[makeHeld()]} />);

    expect(screen.getByText(/decisions needing review/i)).toBeInTheDocument();
    expect(screen.getByText("COLUMN_SWAP")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /investigate/i })).toBeInTheDocument();
  });

  it("counts what is held in the intercepted tile", () => {
    render(
      <Console
        {...baseProps()}
        held={[makeHeld({ id: 1 }), makeHeld({ id: 2, guardian: makeGuardian({ heal_event_id: 11 }) })]}
      />,
    );
    expect(screen.getByText("2 Held")).toBeInTheDocument();
  });

  it("reports no accuracy score rather than a fake 100% when no heal was judged", () => {
    render(<Console {...baseProps()} healEvents={[]} held={[makeHeld()]} />);
    expect(screen.getByText(/no heals judged yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/100\.0%/)).not.toBeInTheDocument();
  });

  it("opens the investigation panel with both numbers and the without/with pair", async () => {
    render(<Console {...baseProps()} held={[makeHeld()]} />);
    await userEvent.click(screen.getByRole("button", { name: /investigate/i }));

    expect(screen.getByText(/historical baseline vs extracted sample/i)).toBeInTheDocument();
    expect(screen.getByText(/without vouch/i)).toBeInTheDocument();
    expect(screen.getByText(/with vouch/i)).toBeInTheDocument();
    expect(screen.getByText(/margin protected/i)).toBeInTheDocument();
  });

  it("says the semantic judge was not consulted rather than implying it was", async () => {
    render(<Console {...baseProps()} held={[makeHeld()]} />);
    await userEvent.click(screen.getByRole("button", { name: /investigate/i }));

    expect(screen.getByText(/what the guardian found/i)).toBeInTheDocument();
    expect(screen.getByText(/semantic judge is consulted only when/i)).toBeInTheDocument();
    expect(screen.queryByText(/tier-3 llm/i)).not.toBeInTheDocument();
  });

  it("asks the real endpoint when the sale audit is selected, sending the pre-sale record", async () => {
    render(<Console {...baseProps()} held={[makeHeld()]} />);
    await switchToSaleAudit();

    await waitFor(() => expect(verify).toHaveBeenCalledTimes(1));
    const body = verify.mock.calls[0][0] as Record<string, unknown>;
    expect(Array.isArray(body.candidate_records)).toBe(true);
    expect(Array.isArray(body.baseline_records)).toBe(true);
    // Without this the check stands down, so its absence would silently produce an empty audit.
    expect(Object.keys(body.reference_prices as object).length).toBeGreaterThan(0);
  });

  it("renders a row per affected product from the endpoint's own evidence", async () => {
    render(<Console {...baseProps()} held={[makeHeld()]} />);
    await switchToSaleAudit();

    expect(await screen.findByText("Voltmart RTX 5090 Titan Liquid 32GB")).toBeInTheDocument();
    expect(screen.getByText("Voltmart RTX 4080 Super Ventus 16GB")).toBeInTheDocument();
    expect(screen.getByText("2 Held")).toBeInTheDocument();

    // The overstatement per row, not the claimed price - the harm is what the column measures.
    // Scoped to the table because the tile also reports the worst case.
    const cells = screen.getAllByRole("cell").map((c) => c.textContent ?? "");
    expect(cells.some((t) => t.includes("1,469.99"))).toBe(true);
    expect(cells.some((t) => t.includes("599.99"))).toBe(true);
    expect(cells.some((t) => t.includes("3,919.98"))).toBe(false);
  });

  it("relabels the harm column per scenario, because it measures a different thing", async () => {
    render(<Console {...baseProps()} held={[makeHeld()]} />);
    expect(
      screen.getByRole("columnheader", { name: /counterfactual risk/i }),
    ).toBeInTheDocument();

    await switchToSaleAudit();
    await screen.findByText("Voltmart RTX 5090 Titan Liquid 32GB");
    expect(
      screen.getByRole("columnheader", { name: /overstated discount/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /counterfactual risk/i })).toBeNull();
  });

  it("offers no Force approve on the audit - there is no proposal of ours to force", async () => {
    render(<Console {...baseProps()} held={[makeHeld()]} />);
    expect(screen.getByRole("button", { name: /force approve/i })).toBeInTheDocument();

    await switchToSaleAudit();
    await screen.findByText("Voltmart RTX 5090 Titan Liquid 32GB");
    expect(screen.queryByRole("button", { name: /force approve/i })).not.toBeInTheDocument();
  });

  it("keeps a dead verification endpoint local instead of blanking the console", async () => {
    verify.mockRejectedValue(new Error("503 upstream"));
    render(<Console {...baseProps()} held={[makeHeld()]} />);
    await switchToSaleAudit();

    expect(await screen.findByText(/could not reach the verification api/i)).toBeInTheDocument();
    expect(screen.getByText(/decisions needing review/i)).toBeInTheDocument();
  });

  it("shows an empty state when nothing is held", () => {
    render(<Console {...baseProps()} held={[]} />);
    expect(screen.getByText(/nothing to hold/i)).toBeInTheDocument();
  });
});
