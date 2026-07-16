import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  expect(await screen.findByText("Lefedettségi részletek")).toBeInTheDocument();
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

test("starts a scan with the selected schemas and optional object types", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const body = url.endsWith("/connection/test") ? {
      success: true,
      capabilities: {
        oracleVersion: "23", databaseName: "TESTDB", containerName: "TESTPDB",
        currentSchema: "READER", driverMode: "thin", schemas: ["SALES"],
        readableViews: ["ALL_OBJECTS"], missingViews: [],
        objectTypes: ["TABLE", "VIEW"], warnings: [],
      },
    } : url.endsWith("/scan") && init?.method === "POST" ? { accepted: true }
      : url.endsWith("/scan/status") ? {
        state: "IDLE", phase: null, progress_current: 0, progress_total: null,
        message: null, error_code: null, error_message: null, counters: {},
        started_at: null, finished_at: null,
      } : url.endsWith("/scan/summary") ? { available: false, summary: null }
        : {
          oracleConfigured: true, oracleMode: "thin", dataFilePresent: false,
          activeOperation: false, limits: {},
        };
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Kapcsolat tesztelése" }));
  fireEvent.click(await screen.findByRole("button", { name: "SALES" }));
  fireEvent.click(await screen.findByText(/Objektumtípus-szűrés/));
  fireEvent.click(await screen.findByRole("button", { name: "TABLE" }));
  fireEvent.click(screen.getByRole("button", { name: "Adatgyűjtés indítása" }));

  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/scan",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ schemas: ["SALES"], objectTypes: ["TABLE"] }),
    }),
  ));
});

test("does not present a completed export as a successful scan", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.endsWith("/scan/status") ? {
      state: "SUCCEEDED", phase: "EXPORTING", progress_current: 0,
      progress_total: null, message: "Operation completed.", error_code: null,
      error_message: null, counters: {}, started_at: "2026-07-15T20:00:00Z",
      finished_at: "2026-07-15T20:00:01Z",
    } : url.endsWith("/scan/summary") ? { available: false, summary: null }
      : url.endsWith("/analyses") ? { items: [] }
        : {
          oracleConfigured: true, oracleMode: "thin", dataFilePresent: true,
          activeOperation: false, limits: {},
        };
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  render(<App />);

  expect(await screen.findByText("IDLE")).toBeInTheDocument();
  expect(screen.queryByRole("progressbar", { name: "Adatgyűjtés befejezve" })).not.toBeInTheDocument();
});

test("searches graph objects without loading the full graph", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const body = url.endsWith("/subgraph") ? {
      rootObjectIds: ["db::pdb::SALES::TABLE::ORDERS"], nodes: [], edges: [],
      truncated: false, suggestion: null,
    } : url.includes("/objects?") ? {
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

  fireEvent.change(screen.getByLabelText("Kapcsolattípusok"), { target: { value: "depends_on, foreign_key" } });
  fireEvent.change(screen.getByLabelText("Minimum confidence"), { target: { value: "0.8" } });
  fireEvent.click(screen.getByLabelText("Külső objektumok"));
  fireEvent.click(screen.getByRole("button", { name: "Gráf" }));
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/subgraph",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        rootObjectIds: ["db::pdb::SALES::TABLE::ORDERS"], depth: 1, direction: "BOTH",
        relationshipTypes: ["DEPENDS_ON", "FOREIGN_KEY"], minimumConfidence: 0.8,
        includeExternal: false,
      }),
    }),
  ));
});

test("shows the complete graph component map after a published scan", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.endsWith("/graph-overview") ? {
      nodes: [],
      edges: [],
      components: [{
        id: "component-1", nodeCount: 12, edgeCount: 11, topology: "TREE",
        density: 0.16, externalNodeCount: 0, invalidNodeCount: 0,
        owners: { SALES: 12 }, objectTypes: { TABLE: 8 },
        relationshipTypes: { DEPENDS_ON: 11 },
        sampleObjects: [{ id: "A", label: "SALES.ORDERS" }],
      }],
      summary: {
        sourceNodeCount: 12, sourceEdgeCount: 11, nodeCount: 12, edgeCount: 11,
        componentCount: 1, isolatedNodeCount: 0, treeComponentCount: 1,
        cyclicComponentCount: 0,
      },
      facets: { owners: { SALES: 12 }, objectTypes: { TABLE: 8 }, statuses: { VALID: 12 }, relationshipTypes: { DEPENDS_ON: 11 } },
    } : url.endsWith("/scan/status") ? {
      state: "SUCCEEDED", phase: "PUBLISHING", progress_current: 1,
      progress_total: 1, message: "Operation completed.", error_code: null,
      error_message: null, counters: {}, started_at: "2026-07-16T07:00:00Z",
      finished_at: "2026-07-16T07:01:00Z",
    } : url.endsWith("/scan/summary") ? { available: false, summary: null }
      : url.endsWith("/analyses") ? { items: [] }
        : { oracleConfigured: true, oracleMode: "thin", dataFilePresent: true, activeOperation: false, limits: {} };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });

  render(<App />);

  expect(await screen.findByText("12 node · 11 él")).toBeInTheDocument();
  expect(screen.getByText("Fa · SALES")).toBeInTheDocument();
  expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/graph-overview",
    expect.objectContaining({ method: "POST" }),
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
        topInternalHubs: [],
        topBridgeObjects: [],
        suggestedName: "SALES / ORDER",
        nameExplanation: "Domináns séma: SALES.",
        stability: "NOT_ASSESSED",
        warnings: [],
      }] };
    } else if (url.endsWith("/analyses/run-1/communities/0")) {
      body = {
        metrics: {
          communityId: 0, nodeCount: 3, internalEdgeCount: 3, externalEdgeCount: 1,
          internalWeight: 9, externalWeight: 0.1, internalDensity: 1,
          externalRatio: 0.01, conductance: 0.01, coverage: 0.49,
          schemaDistribution: { SALES: 3 }, dominantSchema: "SALES",
          dominantSchemaRatio: 1, objectTypeDistribution: { TABLE: 3 },
          topInternalHubs: [{ objectId: "SALES.ORDERS", strength: 9 }],
          topBridgeObjects: [], suggestedName: "SALES / ORDER",
          nameExplanation: "Domináns séma: SALES.", stability: "STABLE",
          stabilityScore: 1, warnings: [],
        },
        nodes: [], annotation: null,
      };
    } else if (url.endsWith("/analyses/run-1/community-graph")) {
      body = { nodes: [{
        communityId: 0, nodeCount: 3, internalEdgeCount: 3, externalEdgeCount: 1,
        internalWeight: 9, externalWeight: 0.1, internalDensity: 1,
        externalRatio: 0.01, conductance: 0.01, coverage: 0.49,
        schemaDistribution: { SALES: 3 }, dominantSchema: "SALES",
        dominantSchemaRatio: 1, objectTypeDistribution: { TABLE: 3 },
        topInternalHubs: [], topBridgeObjects: [], suggestedName: "SALES / ORDER",
        nameExplanation: "Domináns séma: SALES.", stability: "NOT_ASSESSED",
        warnings: [],
      }], edges: [] };
    } else if (url.endsWith("/analyses/resolution-profile") && method === "POST") {
      body = { accepted: true, analysisIds: ["profile-1", "profile-2"] };
    } else if (url.endsWith("/analyses/estimate") && method === "POST") {
      body = {
        estimatedNodeCount: 6, estimatedRelationshipCount: 7,
        sourceNodeCount: 6, sourceRelationshipCount: 7,
        estimatedMemoryBytes: 5760, sizeCategory: "SMALL", withinLimits: true,
        limits: { maxNodes: 500000, maxEdges: 5000000 }, warnings: [], approximate: true,
      };
    } else if (url.endsWith("/analyses/compare") && method === "POST") {
      body = {
        items: [
          { id: "run-1", name: "Domain analysis", config: { resolution: 1 }, summary: {
            communityCount: 2, quality: 12, medianConductance: 0.1, schemaPurity: 1,
          } },
          { id: "run-2", name: "Fine analysis", config: { resolution: 2 }, summary: {
            communityCount: 3, quality: 10, medianConductance: 0.2, schemaPurity: 0.9,
          } },
        ],
        agreement: { sharedNodeCount: 6, pairwise: [{
          leftAnalysisId: "run-1", rightAnalysisId: "run-2",
          adjustedRandIndex: 0.8, normalizedMutualInformation: 0.85,
          variationOfInformation: 0.2,
        }], communityStability: [], thresholds: { stable: 0.8, mixed: 0.55 } },
      };
    } else if (url.endsWith("/annotations") && method === "POST") {
      body = {
        id: "annotation-1", analysisId: "run-1", communityId: 0,
        name: "Sales order", note: "Verified", createdAt: "now", updatedAt: "now",
      };
    } else if (url.endsWith("/export") && method === "POST") {
      body = { accepted: true, exportId: "export-1" };
    } else if (url.endsWith("/export/export-1/status")) {
      body = {
        id: "export-1", analysisId: "run-1", format: "JSON", status: "SUCCEEDED",
        filename: "analysis.json", contentType: "application/json", errorMessage: null,
        downloadUrl: "/api/export/export-1/file",
      };
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
      }, {
        id: "run-2", name: "Fine analysis", status: "SUCCEEDED", algorithm: "LEIDEN",
        config: { resolution: 2 }, summary: {
          algorithm: "LEIDEN", objective: "CPM", resolution: 2, quality: 10,
          communityCount: 3, communitySizes: [2, 2, 2], singletonCount: 0,
          smallCommunityCount: 3, isolatedNodeCount: 0, sharedInfrastructureCount: 0,
          internalWeightRatio: 0.8, averageConductance: 0.2, medianConductance: 0.2,
          schemaPurity: 0.9, runtimeSeconds: 0.03, pipelineCounts: {},
        }, errorMessage: null, createdAt: "2026-07-15T00:00:02Z",
        startedAt: "2026-07-15T00:00:02Z", finishedAt: "2026-07-15T00:00:03Z",
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
  expect(await screen.findByText("6 node · 7 kapcsolat")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Kapcsolattípus-súlyok"));
  fireEvent.change(screen.getByLabelText("Idegen kulcs súlya"), { target: { value: "7" } });
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/analyses/estimate",
    expect.objectContaining({ body: expect.stringContaining('"FOREIGN_KEY":7') }),
  ));
  fireEvent.click(await screen.findByText("Domain analysis"));
  expect(await screen.findByText("SALES / ORDER")).toBeInTheDocument();
  expect(screen.getByText("90.0%")).toBeInTheDocument();

  fireEvent.click(screen.getAllByRole("button", { name: /SALES \/ ORDER/ })[0]);
  const detail = await screen.findByText("Miért került ide?");
  const detailCard = detail.closest(".community-detail-card");
  expect(detailCard).not.toBeNull();
  fireEvent.change(within(detailCard as HTMLElement).getByLabelText("Név"), { target: { value: "Sales order" } });
  fireEvent.change(within(detailCard as HTMLElement).getByLabelText("Megjegyzés"), { target: { value: "Verified" } });
  fireEvent.click(within(detailCard as HTMLElement).getByRole("button", { name: "Mentés" }));
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/annotations", expect.objectContaining({ method: "POST" }),
  ));

  fireEvent.click(screen.getByLabelText("Domain analysis összehasonlítása"));
  fireEvent.click(screen.getByLabelText("Fine analysis összehasonlítása"));
  fireEvent.click(screen.getByRole("button", { name: "Kijelöltek összehasonlítása (2)" }));
  expect(await screen.findByText("ARI")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "JSON" }));
  expect(await screen.findByRole("link", { name: "analysis.json" })).toHaveAttribute(
    "href", "/api/export/export-1/file",
  );

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

test("starts an analysis even while the background estimate is still loading", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/analyses/estimate")) {
      return new Promise<Response>(() => {});
    }
    const body = url.endsWith("/analyses") && method === "POST"
      ? { accepted: true, analysisId: "analysis-new" }
      : url.endsWith("/analyses") ? { items: [] }
        : url.endsWith("/scan/status") ? {
          state: "IDLE", phase: null, progress_current: 0, progress_total: null,
          message: null, error_code: null, error_message: null, counters: {},
          started_at: null, finished_at: null,
        } : url.endsWith("/scan/summary") ? { available: false, summary: null }
          : { oracleConfigured: true, oracleMode: "thin", dataFilePresent: true, activeOperation: false, limits: {} };
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  render(<App />);
  const startButton = await screen.findByRole("button", { name: "Elemzés indítása" });
  expect(startButton).toBeEnabled();
  const analysisForm = startButton.closest("form") as HTMLFormElement;
  expect(analysisForm.noValidate).toBe(true);
  expect(analysisForm.checkValidity()).toBe(true);
  fireEvent.click(startButton);

  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/analyses",
    expect.objectContaining({ method: "POST" }),
  ));
});

test("starts an experimental hierarchy with recursive parameters", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = url.endsWith("/analyses/hierarchy") && method === "POST" ? {
      accepted: true, analysisId: "hierarchy-1", experimental: true,
    } : url.endsWith("/analyses/estimate") ? {
      estimatedNodeCount: 100, estimatedRelationshipCount: 200,
      sourceNodeCount: 100, sourceRelationshipCount: 200,
      estimatedMemoryBytes: 128000, sizeCategory: "SMALL", withinLimits: true,
      limits: { maxNodes: 500000, maxEdges: 5000000 }, warnings: [], approximate: true,
    } : url.endsWith("/analyses") ? { items: [] }
      : url.endsWith("/scan/status") ? {
        state: "IDLE", phase: null, progress_current: 0, progress_total: null,
        message: null, error_code: null, error_message: null, counters: {},
        started_at: null, finished_at: null,
      } : url.endsWith("/scan/summary") ? { available: false, summary: null }
        : { oracleConfigured: true, oracleMode: "thin", dataFilePresent: true, activeOperation: false, limits: {} };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });

  render(<App />);
  expect(await screen.findByText("100 node · 200 kapcsolat")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Kísérleti hierarchia beállításai"));
  fireEvent.change(screen.getByLabelText("Hierarchia alap resolution"), { target: { value: "0.1" } });
  fireEvent.change(screen.getByLabelText("Hierarchia gyermek resolution"), { target: { value: "1.5" } });
  fireEvent.change(screen.getByLabelText("Hierarchia minimum méret"), { target: { value: "12" } });
  fireEvent.change(screen.getByLabelText("Hierarchia maximum mélység"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Hierarchia maximum közösség"), { target: { value: "500" } });
  fireEvent.change(screen.getByLabelText("Hierarchia resolution felülírások"), { target: { value: "0=2.5" } });
  fireEvent.click(screen.getByRole("button", { name: "Kísérleti hierarchia indítása" }));

  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/analyses/hierarchy",
    expect.objectContaining({
      method: "POST",
      body: expect.stringContaining('"hierarchyResolutionOverrides":{"0":2.5}'),
    }),
  ));
  const call = vi.mocked(globalThis.fetch).mock.calls.find(([url]) => String(url).endsWith("/analyses/hierarchy"));
  const payload = JSON.parse(String((call?.[1] as RequestInit).body));
  expect(payload).toMatchObject({
    resolution: 0.1, hierarchyChildResolution: 1.5,
    hierarchyMinimumSize: 12, hierarchyMaxDepth: 2, hierarchyMaxCommunities: 500,
  });
});

test("renders and drills into a persisted hierarchy tree", async () => {
  const metrics = {
    communityId: 0, nodeCount: 3, internalEdgeCount: 3, externalEdgeCount: 0,
    internalWeight: 9, externalWeight: 0, internalDensity: 1, externalRatio: 0,
    conductance: 0, coverage: 1, schemaDistribution: { SALES: 3 },
    dominantSchema: "SALES", dominantSchemaRatio: 1, objectTypeDistribution: { TABLE: 3 },
    topInternalHubs: [], topBridgeObjects: [], suggestedName: "SALES / ORDER",
    nameExplanation: "Domináns séma: SALES.", stability: "NOT_ASSESSED", warnings: [],
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.endsWith("/analyses/hierarchy-run/hierarchy/0") ? {
      hierarchyId: "0", parentId: null, level: 0, resolution: 0.2,
      splitResolution: 1, splitQuality: 2, nodeCount: 3, stopReason: "NO_SPLIT",
      metrics, objects: [{
        id: "A", owner: "SALES", name: "ORDERS", objectType: "TABLE",
        oracleObjectType: "TABLE", status: "VALID", isExternal: false, metadata: {},
      }],
    } : url.endsWith("/analyses/hierarchy-run/hierarchy") ? {
      analysisId: "hierarchy-run", experimental: true,
      summary: {
        baseResolution: 0.2, defaultChildResolution: 1, minimumSplitSize: 20,
        maximumDepth: 3, rootCount: 1, hierarchyNodeCount: 1, leafCount: 1,
        maximumDepthReached: 0, maximumCommunities: 10000,
        resolutionOverrides: {}, unusedResolutionOverrideIds: [], leafMembershipCount: 3,
        truncated: false, warning: "Kísérleti felosztás.",
      },
      roots: [{
        hierarchyId: "0", parentId: null, level: 0, resolution: 0.2,
        splitResolution: 1, splitQuality: 2, nodeCount: 3, stopReason: "NO_SPLIT",
        metrics, childrenCount: 0, children: [],
      }],
    } : url.endsWith("/analyses/hierarchy-run/communities") ? { items: [] }
      : url.endsWith("/analyses/hierarchy-run/community-graph") ? { nodes: [], edges: [] }
        : url.endsWith("/analyses") ? { items: [{
          id: "hierarchy-run", name: "Hierarchy run", status: "SUCCEEDED", algorithm: "LEIDEN",
          config: { resolution: 0.2, hierarchyEnabled: true },
          summary: {
            algorithm: "LEIDEN", objective: "CPM", resolution: 0.2, quality: 1,
            communityCount: 1, communitySizes: [3], singletonCount: 0,
            smallCommunityCount: 0, isolatedNodeCount: 0, sharedInfrastructureCount: 0,
            internalWeightRatio: 1, averageConductance: 0, medianConductance: 0,
            schemaPurity: 1, runtimeSeconds: 0.01, pipelineCounts: {},
          }, errorMessage: null, createdAt: "now", startedAt: "now", finishedAt: "now",
        }] } : url.endsWith("/analyses/estimate") ? {
          estimatedNodeCount: 3, estimatedRelationshipCount: 3, sourceNodeCount: 3,
          sourceRelationshipCount: 3, estimatedMemoryBytes: 3000, sizeCategory: "SMALL",
          withinLimits: true, limits: { maxNodes: 500000, maxEdges: 5000000 },
          warnings: [], approximate: true,
        } : url.endsWith("/scan/status") ? {
          state: "IDLE", phase: null, progress_current: 0, progress_total: null,
          message: null, error_code: null, error_message: null, counters: {},
          started_at: null, finished_at: null,
        } : url.endsWith("/scan/summary") ? { available: false, summary: null }
          : { oracleConfigured: true, oracleMode: "thin", dataFilePresent: true, activeOperation: false, limits: {} };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  });

  render(<App />);
  fireEvent.click(await screen.findByText("Hierarchy run"));
  expect(await screen.findByText("Hierarchikus közösségtérkép")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /SALES \/ ORDER/ }));
  expect(await screen.findByText("SALES.ORDERS · TABLE")).toBeInTheDocument();
});
