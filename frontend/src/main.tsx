import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { MotionConfig } from "framer-motion";
import { HintProvider } from "./components/Hint";
import "./styles.css";

const client = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <HintProvider delayDuration={200}>
          {/* Every framer-motion animation honours the OS "reduce motion" setting. */}
          <MotionConfig reducedMotion="user">
            <App />
          </MotionConfig>
        </HintProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
