import { createRoot } from "react-dom/client";
import App from "./App";
import ErrorBoundary from "./ErrorBoundary";
import "../index.css";

// Kiosk hardening: this runs on a public hospital touchscreen, not a personal
// device - a patient right-clicking into "Inspect"/"View source" isn't a
// scenario worth supporting. Harmless for normal development too (F12 still
// opens devtools regardless of this).
document.addEventListener("contextmenu", (event) => event.preventDefault());

createRoot(document.getElementById("root")).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
