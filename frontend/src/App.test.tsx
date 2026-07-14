import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => vi.restoreAllMocks());

test("shows the configured Oracle connection", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
    oracleConfigured: true,
    oracleMode: "thin",
    dataFilePresent: true,
    activeOperation: false,
    limits: {},
  }), { status: 200, headers: { "Content-Type": "application/json" } }));

  render(<App />);
  expect(await screen.findByText("Beállítva")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Kapcsolat tesztelése" })).toBeEnabled();
});
