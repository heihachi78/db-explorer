import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

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

test("searches graph objects without loading the full graph", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.includes("/objects?") ? {
      items: [{
        id: "db::pdb::SALES::TABLE::ORDERS",
        owner: "SALES",
        name: "ORDERS",
        objectType: "TABLE",
        oracleObjectType: "TABLE",
        status: "VALID",
        isExternal: false,
        metadata: {},
      }],
      total: 1,
      page: 1,
      pageSize: 30,
      facets: { owners: { SALES: 1 }, objectTypes: { TABLE: 1 }, statuses: { VALID: 1 } },
    } : url.endsWith("/scan/status") ? {
      state: "IDLE", phase: null, progress_current: 0, progress_total: null,
      message: null, error_code: null, error_message: null, counters: {},
      started_at: null, finished_at: null,
    } : url.endsWith("/scan/summary") ? { available: false, summary: null } : {
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
  fireEvent.change(await screen.findByPlaceholderText("például ORDER*"), { target: { value: "ORDER*" } });
  fireEvent.click(await screen.findByRole("button", { name: "Keresés" }));

  expect(await screen.findByText("SALES.ORDERS")).toBeInTheDocument();
  expect(screen.getByText("TABLE")).toBeInTheDocument();
  expect(globalThis.fetch).toHaveBeenCalledWith(
    expect.stringContaining("/api/objects?q=ORDER*&pageSize=30"),
    expect.any(Object),
  );
});

test("shows persisted analysis metrics and starts a resolution profile", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    let body: unknown;
    if (url.endsWith("/analyses/run-1/communities")) {
      body = { items: [{
        communityId: 0,
        nodeCount: 3,
        internalEdgeCount: 3,
        externalEdgeCount: 1,
        internalWeight: 9,
        externalWeight: 0.1,
        internalDensity: 1,
        externalRatio: 0.01,
        conductance: 0.01,
        coverage: 0.49,
        schemaDistribution: { SALES: 3 },
        dominantSchema: "SALES",
        dominantSchemaRatio: 1,
        objectTypeDistribution: { TABLE: 3 },
        warnings: [],
      }] };
    } else if (url.endsWith("/analyses/resolution-profile") && method === "POST") {
      body = { accepted: true, analysisIds: ["profile-1", "profile-2"] };
    } else if (url.endsWith("/analyses")) {
      body = { items: [{
        id: "run-1",
        name: "Domain analysis",
        status: "SUCCEEDED",
        algorithm: "LEIDEN",
        config: { resolution: 1 },
        summary: {
          algorithm: "LEIDEN", objective: "CPM", resolution: 1, quality: 12,
          communityCount: 2, communitySizes: [3, 3], singletonCount: 0,
          smallCommunityCount: 0, isolatedNodeCount: 0,
          sharedInfrastructureCount: 0, internalWeightRatio: 0.9,
          averageConductance: 0.1, medianConductance: 0.1,
          schemaPurity: 1, runtimeSeconds: 0.02, pipelineCounts: {},
        },
        errorMessage: null,
        createdAt: "2026-07-15T00:00:00Z",
        startedAt: "2026-07-15T00:00:00Z",
        finishedAt: "2026-07-15T00:00:01Z",
      }] };
    } else if (url.endsWith("/scan/status")) {
      body = {
        state: "IDLE", phase: null, progress_current: 0, progress_total: null,
        message: null, error_code: null, error_message: null, counters: {},
        started_at: null, finished_at: null,
      };
    } else if (url.endsWith("/scan/summary")) {
      body = { available: false, summary: null };
    } else {
      body = {
        oracleConfigured: true, oracleMode: "thin", dataFilePresent: true,
        activeOperation: false, limits: {},
      };
    }
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  render(<App />);
  fireEvent.click(await screen.findByText("Domain analysis"));
  expect(await screen.findByText("SALES · 100.0%")).toBeInTheDocument();
  expect(screen.getByText("90.0%")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "6 pontos resolution profil" }));
  expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/analyses/resolution-profile",
    expect.objectContaining({ method: "POST" }),
  );
});

test("disables analysis starts while a scan is active", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.endsWith("/scan/status") ? {
      state: "EXTRACTING_OBJECTS", phase: "EXTRACTING_OBJECTS",
      progress_current: 4, progress_total: 10, message: "Scanning",
      error_code: null, error_message: null, counters: {},
      started_at: "2026-07-15T00:00:00Z", finished_at: null,
    } : url.endsWith("/scan/summary") ? { available: false, summary: null }
      : url.endsWith("/analyses") ? { items: [] }
        : {
          oracleConfigured: true, oracleMode: "thin", dataFilePresent: true,
          activeOperation: true, limits: {},
        };
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  render(<App />);

  expect(await screen.findByRole("button", { name: "Elemzés indítása" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "6 pontos resolution profil" })).toBeDisabled();
});
