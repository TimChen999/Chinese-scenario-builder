/**
 * React entry point. Wires up the global providers (React Query,
 * React Router) and mounts the <App /> tree. See DESIGN.md
 * Section 8.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import "./styles/index.css";

/**
 * The single QueryClient lives at the app root so every hook shares
 * the cache. Defaults are intentionally conservative: TanStack's
 * built-in retry doubles up against our own polling, so we disable
 * it for everything except mutations (handled per-call).
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
