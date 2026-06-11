import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { initSentry } from "@/lib/sentry";

// Kick off Sentry before the first render so even boot-time errors get
// captured. No-op when REACT_APP_SENTRY_DSN is unset.
initSentry();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
