/**
 * The catalogue, folded away by default.
 *
 * It is reference material, not a decision. Open at full height it competed with the incident card
 * for attention and pushed it off a projector screen.
 */

import { money } from "../format";
import type { Product } from "../types";
import { Disclosure } from "./ui/Bits";

export function Catalogue({ products }: { products: Product[] }) {
  return (
    <Disclosure
      title="Catalogue"
      count={products.length}
      hint="what we sell, and where each price stands"
    >
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-hair text-left text-ink-muted">
            <th className="px-5 py-2 font-normal">SKU</th>
            <th className="px-3 py-2 font-normal">Our price</th>
            <th className="px-3 py-2 font-normal">Floor</th>
            <th className="px-3 py-2 font-normal">Competitor</th>
            <th className="px-5 py-2 font-normal">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hair">
          {products.map((product) => (
            <tr key={product.id} className="hover:bg-raised/40">
              <td className="px-5 py-2">
                <span className="text-ink">{product.sku}</span>
                <span className="ml-2 text-ink-muted">{product.name}</span>
              </td>
              <td className="num px-3 py-2 text-ink">{money(product.my_price)}</td>
              <td className="num px-3 py-2 text-ink-muted">{money(product.floor_price)}</td>
              <td className="num px-3 py-2 text-ink-secondary">
                {product.last_confirmed_price === null
                  ? "—"
                  : money(product.last_confirmed_price)}
              </td>
              <td className="px-5 py-2">
                <span
                  className={
                    product.source_confirmed ? "text-ink-muted" : "text-status-critical"
                  }
                >
                  {product.source_confirmed ? product.last_confirmed_label : "unconfirmed"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Disclosure>
  );
}
