import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => vi.restoreAllMocks());

test("shows the configured Oracle connection", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.endsWith("/scan/status") ? {
      state: "IDLE",
      phase: null,
      progress_current: 0,
      progress_total: null,
      message: null,
      error_code: null,
      error_message: null,
      counters: {},
      started_at: null,
      finished_at: null,
    } : url.endsWith("/scan/summary") ? {
      available: true,
      summary: {
        databaseName: "TESTDB",
        containerName: "TESTPDB",
        selectedSchemas: ["SALES"],
        ownerCounts: { SALES: 2 },
        objectTypeCounts: { TABLE: 2 },
        relationshipTypeCounts: { DEPENDS_ON: 1 },
        externalObjectCount: 0,
        unresolvedSynonymCount: 0,
        warnings: [],
      },
    } : {
      oracleConfigured: true,
      oracleMode: "thin",
      dataFilePresent: true,
      activeOperation: false,
      limits: {},
    };
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  render(<App />);
  expect(await screen.findByText("Beállítva")).toBeInTheDocument();
  expect(await screen.findByText("Objektum")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Kapcsolat tesztelése" })).toBeEnabled();
});

test("shows a static completed progress bar without stale phase labels", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.endsWith("/scan/status") ? {
      state: "SUCCEEDED",
      phase: "PUBLISHING",
      progress_current: 0,
      progress_total: null,
      message: "Operation completed.",
      error_code: null,
      error_message: null,
      counters: {},
      started_at: "2026-07-14T20:00:00Z",
      finished_at: "2026-07-14T20:01:00Z",
    } : url.endsWith("/scan/summary") ? {
      available: true,
      summary: {
        databaseName: "TESTDB",
        containerName: "TESTPDB",
        selectedSchemas: ["SALES"],
        ownerCounts: { SALES: 2 },
        objectTypeCounts: { TABLE: 2 },
        relationshipTypeCounts: { DEPENDS_ON: 1 },
        externalObjectCount: 0,
        unresolvedSynonymCount: 0,
        warnings: [],
      },
    } : {
      oracleConfigured: true,
      oracleMode: "thin",
      dataFilePresent: true,
      activeOperation: false,
      limits: {},
    };
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  render(<App />);

  const progress = await screen.findByRole("progressbar", { name: "Adatgyűjtés befejezve" });
  expect(progress).toHaveAttribute("value", "1");
  expect(progress).toHaveAttribute("max", "1");
  expect(screen.queryByText("PUBLISHING")).not.toBeInTheDocument();
  expect(screen.queryByText("Operation completed.")).not.toBeInTheDocument();
});
