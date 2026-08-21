import React from "react";
import ReactDOM from "react-dom/client";

// Fonts are bundled, not fetched from a CDN. This console's whole premise is that it runs offline
// and deterministically; a typeface that silently falls back when the network is unavailable would
// contradict that in the most visible way possible. Only the weights actually used are imported.
import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/700.css";
// Bricolage Grotesque (variable) carries the display/editorial voice — the big type is the drama.
import "@fontsource-variable/bricolage-grotesque";

import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
