/**
 * The examples page carries the architectural claim: the same guardian, two consumers, one table.
 *
 * So these tests care about the seam rather than the styling — that switching case really re-asks the
 * guardian instead of relabelling the same rows, that the sale audit renders numbers the ENDPOINT
 * returned, and that neither example claims something it was not told.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Examples } from "./Examples";
import { makeGuardian, makeHealEvent, makeHeld } from "../test/fixtures";

const verify = vi.fn();

vi.mock("../api", () => ({
  api: { verify: (...args: unknown[]) => verify(...args) },
}));

/** One aggregated REFERENCE_PRICE_UNSUPPORTED result, shaped as the backend returns it. */
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

function props() {
  return { held: [makeHeld()], healEvents: [makeHealEvent()] };
}

const openAudit = () => userEvent.click(screen.getByRole("tab", { name: /sale price audit/i }));

describe("Examples", () => {
  beforeEach(() => {
    verify.mockReset();
    verify.mockResolvedValue(saleResponse());
  });

  it("presents the two cases as separate, numbered examples", () => {
    render(<Examples {...props()} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(2);
    expect(tabs[0]).toHaveTextContent(/competitive repricing/i);
    expect(tabs[1]).toHaveTextContent(/sale price audit/i);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
  });

  it("opens directly on the case the Demo menu deep-linked to", () => {
    render(<Examples {...props()} initialCase="sale-audit" />);
    expect(screen.getByRole("tab", { name: /sale price audit/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("leads each example with what broke and what it cost, before any table", () => {
    render(<Examples {...props()} />);
    expect(screen.getByText(/what happened/i)).toBeInTheDocument();
    expect(screen.getByText(/reading the delivery cost into the price field/i)).toBeInTheDocument();
    expect(screen.getByText("COLUMN_SWAP")).toBeInTheDocument();
  });

  it("asks the real endpoint for the audit, sending the pre-sale record", async () => {
    render(<Examples {...props()} />);
    await openAudit();

    await waitFor(() => expect(verify).toHaveBeenCalledTimes(1));
    const body = verify.mock.calls[0][0] as Record<string, unknown>;
    expect(Array.isArray(body.candidate_records)).toBe(true);
    // Without this the check stands down, so its absence would silently produce an empty audit.
    expect(Object.keys(body.reference_prices as object).length).toBeGreaterThan(0);
  });

  it("draws one row per affected product from the endpoint's own evidence", async () => {
    render(<Examples {...props()} />);
    await openAudit();

    expect(await screen.findByText("Voltmart RTX 5090 Titan Liquid 32GB")).toBeInTheDocument();
    expect(screen.getByText("Voltmart RTX 4080 Super Ventus 16GB")).toBeInTheDocument();

    // The overstatement per row, not the claimed price - the harm is what the column measures.
    const cells = screen.getAllByRole("cell").map((c) => c.textContent ?? "");
    expect(cells.some((t) => t.includes("1,469.99"))).toBe(true);
    expect(cells.some((t) => t.includes("3,919.98"))).toBe(false);
  });

  it("relabels the harm column per example, because it measures a different thing", async () => {
    render(<Examples {...props()} />);
    expect(screen.getByRole("columnheader", { name: /counterfactual risk/i })).toBeInTheDocument();

    await openAudit();
    await screen.findByText("Voltmart RTX 5090 Titan Liquid 32GB");
    expect(screen.getByRole("columnheader", { name: /overstated discount/i })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: /counterfactual risk/i })).toBeNull();
  });

  it("distinguishes a rejected heal from a correct heal over a dishonest page", async () => {
    render(<Examples {...props()} />);
    expect(screen.getByText(/extraction was wrong/i)).toBeInTheDocument();

    await openAudit();
    await screen.findByText("Voltmart RTX 5090 Titan Liquid 32GB");
    expect(screen.getByText(/extraction was right/i)).toBeInTheDocument();
    expect(screen.getByText("PASS")).toBeInTheDocument();
  });

  it("opens an investigation with both numbers and the without/with pair", async () => {
    render(<Examples {...props()} />);
    await userEvent.click(screen.getByRole("button", { name: /investigate/i }));

    expect(screen.getByText(/historical baseline vs extracted sample/i)).toBeInTheDocument();
    expect(screen.getByText(/without vouch/i)).toBeInTheDocument();
    expect(screen.getByText(/with vouch/i)).toBeInTheDocument();
  });

  it("says the semantic judge was not consulted rather than implying it was", async () => {
    render(<Examples {...props()} />);
    await userEvent.click(screen.getByRole("button", { name: /investigate/i }));

    expect(screen.getByText(/what the guardian found/i)).toBeInTheDocument();
    expect(screen.queryByText(/tier-3 llm/i)).not.toBeInTheDocument();
  });

  it("reports no accuracy figure rather than a fake one when no heal was judged", () => {
    render(<Examples held={[makeHeld()]} healEvents={[]} />);
    expect(screen.getByText(/heals judged/i)).toBeInTheDocument();
    expect(screen.queryByText(/mean 100/i)).not.toBeInTheDocument();
  });

  it("keeps a dead verification endpoint local instead of blanking the page", async () => {
    verify.mockRejectedValue(new Error("503 upstream"));
    render(<Examples {...props()} />);
    await openAudit();

    expect(await screen.findByText(/could not reach the verification api/i)).toBeInTheDocument();
    expect(screen.getAllByRole("tab")).toHaveLength(2);
  });

  it("tells you how to produce a hold when the repricing example has none", () => {
    render(<Examples held={[]} healEvents={[makeHealEvent()]} />);
    expect(screen.getByText(/nothing held in this example/i)).toBeInTheDocument();
    expect(screen.getByText(/demo control on the console/i)).toBeInTheDocument();
  });

  it("counts several holds from one bad heal as several rows", () => {
    render(
      <Examples
        held={[makeHeld({ id: 1 }), makeHeld({ id: 2, guardian: makeGuardian({ heal_event_id: 11 }) })]}
        healEvents={[makeHealEvent()]}
      />,
    );
    expect(screen.getByText("2 Held")).toBeInTheDocument();
  });
});
