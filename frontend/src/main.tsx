import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import { initObservability } from "@/lib/observability";
import { initAnalytics } from "@/lib/analytics";

// Started before render so an error during the first paint is captured.
initObservability("website");
initAnalytics();

createRoot(document.getElementById("root")!).render(<App />);
