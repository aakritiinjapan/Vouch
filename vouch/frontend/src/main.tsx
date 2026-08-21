import React from "react";
import ReactDOM from "react-dom/client";

// Fonts are bundled, not fetched from a CDN. This console's whole premise is that it runs offline
// and deterministically; a typeface that silently falls back when the network is unavailable would
// contradict that in the most visible way possible. Only the weights actually used are imported.
import "@fontsource/chivo/400.css";
import "@fontsource/chivo/500.css";
import "@fontsource/chivo/600.css";
import "@fontsource/chivo/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/700.css";
// Fraunces (variable) carries the display/verdict voice — serif = pronouncement.
import "@fontsource-variable/fraunces";

import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
