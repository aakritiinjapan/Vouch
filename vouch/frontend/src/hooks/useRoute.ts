/**
 * Tiny hash-based router. No dependency, no history rewrites — the whole app is four surfaces and a
 * couple of query params ("view as API" preloads a scenario), which a hash handles without pulling in
 * react-router. `#/` → hero, `#/console` → console, `#/examples?case=sale-audit` → the worked
 * examples, `#/trust-api?scenario=column-swap` → Trust API.
 */

import { useCallback, useEffect, useState } from "react";

export type View = "home" | "console" | "examples" | "trust-api";

const VIEWS: View[] = ["console", "examples", "trust-api"];

export interface Route {
  view: View;
  params: URLSearchParams;
}

function parse(): Route {
  const hash = window.location.hash.replace(/^#/, "");
  const [path, query = ""] = hash.split("?");
  const clean = path.replace(/^\//, "") as View;
  const view: View = VIEWS.includes(clean) ? clean : "home";
  return { view, params: new URLSearchParams(query) };
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parse());

  useEffect(() => {
    const onHash = () => setRoute(parse());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const navigate = useCallback((view: View, params?: Record<string, string>) => {
    const query = params ? new URLSearchParams(params).toString() : "";
    const path = view === "home" ? "/" : `/${view}`;
    window.location.hash = query ? `${path}?${query}` : path;
    // Some browsers coalesce identical hash writes; keep state honest either way.
    setRoute({ view, params: new URLSearchParams(query) });
  }, []);

  return { route, navigate };
}

export type Navigate = ReturnType<typeof useRoute>["navigate"];
