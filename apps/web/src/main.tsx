import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import "./i18n";

// A redeploy replaces hashed chunks; a tab left open on the previous build then
// requests a file the server no longer has, and Vite surfaces the failed dynamic
// import as `vite:preloadError`. Reload once to pick up the new shell, guarded so
// a genuinely missing chunk cannot loop. Reaching this module means the shell
// loaded, so the guard is cleared for future deploys in the same tab.
const PRELOAD_RELOAD_KEY = "vite:preloadError:reloaded";

window.addEventListener("vite:preloadError", () => {
    if (sessionStorage.getItem(PRELOAD_RELOAD_KEY)) return;
    sessionStorage.setItem(PRELOAD_RELOAD_KEY, "1");
    window.location.reload();
});

ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>
);

sessionStorage.removeItem(PRELOAD_RELOAD_KEY);
