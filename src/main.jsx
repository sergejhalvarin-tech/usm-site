import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import "./styles.css";

/* `?webgl1` — test the site as an old phone sees it: WebGL 2 is hidden, three.js falls back to WebGL 1 */
if (new URLSearchParams(location.search).has("webgl1")) {
  const get = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, ...a) { return type === "webgl2" ? null : get.call(this, type, ...a); };
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
