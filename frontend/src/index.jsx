import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";
import { ThemeProvider } from "@/context/ThemeContext";
import { setAppQueryClient } from "@/lib/queryClient";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Company/departments keep a longer window via their own hooks.
      // useFetch pages use FETCH_STALE_MS (5s) and write-path invalidation.
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});
setAppQueryClient(queryClient);

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
