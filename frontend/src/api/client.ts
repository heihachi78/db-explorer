export interface PublicConfig {
  oracleConfigured: boolean;
  oracleMode: "thin" | "thick";
  dataFilePresent: boolean;
  activeOperation: boolean;
  limits: Record<string, number>;
}

export interface Capabilities {
  oracleVersion: string;
  databaseName: string;
  containerName: string;
  currentSchema: string;
  driverMode: string;
  schemas: string[];
  readableViews: string[];
  missingViews: string[];
  objectTypes: string[];
  dbmsMetadataGetDdl: boolean;
  warnings: string[];
}

export interface ScanStatus {
  state: string;
  phase: string | null;
  progress_current: number;
  progress_total: number | null;
  message: string | null;
  error_code: string | null;
  error_message: string | null;
  counters: Record<string, number>;
  started_at: string | null;
  finished_at: string | null;
}

export interface ScanSummary {
  databaseName: string;
  containerName: string;
  selectedSchemas: string[];
  ownerCounts: Record<string, number>;
  objectTypeCounts: Record<string, number>;
  relationshipTypeCounts: Record<string, number>;
  externalObjectCount: number;
  unresolvedSynonymCount: number;
  warnings: string[];
}

export interface GraphNode {
  id: string;
  owner: string;
  name: string;
  objectType: string;
  oracleObjectType: string;
  status: string | null;
  isExternal: boolean;
  metadata: Record<string, unknown>;
  depth?: number;
}

export interface GraphEvidence {
  sourceView: string;
  details: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relationshipType: string;
  directed: boolean;
  confidence: number;
  origin: string;
  metadata: Record<string, unknown>;
  evidence: GraphEvidence[];
}

export interface ObjectSearchResult {
  items: GraphNode[];
  total: number;
  page: number;
  pageSize: number;
  facets: {
    owners: Record<string, number>;
    objectTypes: Record<string, number>;
    statuses: Record<string, number>;
  };
}

export interface SubgraphResult {
  rootObjectIds: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  suggestion: string | null;
}

export interface PathResult {
  sourceId: string;
  targetId: string;
  mode: "HOPS" | "WEIGHTED";
  directed: boolean;
  paths: Array<{
    nodes: GraphNode[];
    edges: GraphEdge[];
    hops: number;
    totalCost: number;
  }>;
  truncated: boolean;
}

export interface AnalysisSummary {
  algorithm: string;
  objective: string;
  resolution: number;
  quality: number;
  communityCount: number;
  communitySizes: number[];
  singletonCount: number;
  smallCommunityCount: number;
  isolatedNodeCount: number;
  sharedInfrastructureCount: number;
  internalWeightRatio: number;
  averageConductance: number;
  medianConductance: number;
  schemaPurity: number;
  runtimeSeconds: number;
  pipelineCounts: Record<string, number>;
  stability?: {
    sharedNodeCount: number;
    pairwise: PartitionAgreement[];
    thresholds: { stable: number; mixed: number };
  };
}

export interface AnalysisRun {
  id: string;
  name: string;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  algorithm: string;
  config: Record<string, unknown>;
  summary: AnalysisSummary | null;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface CommunityMetrics {
  communityId: number;
  nodeCount: number;
  internalEdgeCount: number;
  externalEdgeCount: number;
  internalWeight: number;
  externalWeight: number;
  internalDensity: number;
  externalRatio: number;
  conductance: number;
  coverage: number;
  schemaDistribution: Record<string, number>;
  dominantSchema: string;
  dominantSchemaRatio: number;
  objectTypeDistribution: Record<string, number>;
  topInternalHubs: Array<{ objectId: string; strength: number }>;
  topBridgeObjects: Array<{ objectId: string; externalStrength: number }>;
  suggestedName: string;
  nameExplanation: string;
  stability: "NOT_ASSESSED" | "STABLE" | "MIXED" | "UNSTABLE";
  stabilityScore?: number;
  warnings: string[];
  annotation?: Annotation | null;
}

export interface Annotation {
  id: string;
  analysisId: string;
  communityId: number;
  name: string | null;
  note: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CommunityDetail {
  metrics: CommunityMetrics;
  nodes: Array<GraphNode & { centrality: Record<string, number> }>;
  annotation: Annotation | null;
}

export interface CommunityGraph {
  nodes: CommunityMetrics[];
  edges: Array<{
    sourceCommunity: number;
    targetCommunity: number;
    edgeCount: number;
    totalWeight: number;
    forwardWeight: number;
    reverseWeight: number;
    relationshipTypeDistribution: Record<string, number>;
    bridgePairs: Array<{ source: string; target: string; weight: number }>;
  }>;
}

export interface PartitionAgreement {
  leftAnalysisId: string;
  rightAnalysisId: string;
  adjustedRandIndex: number;
  normalizedMutualInformation: number;
  variationOfInformation: number;
}

export interface AnalysisComparison {
  items: Array<Pick<AnalysisRun, "id" | "name" | "config" | "summary">>;
  agreement: {
    sharedNodeCount: number;
    pairwise: PartitionAgreement[];
    communityStability: Array<{ communityId: number; score: number; label: string }>;
    thresholds: { stable: number; mixed: number };
  };
}

export interface ExportJob {
  id: string;
  analysisId: string;
  format: "JSON" | "CSV" | "SVG" | "PNG";
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  filename: string | null;
  contentType: string | null;
  errorMessage: string | null;
  downloadUrl: string | null;
}

interface ApiErrorBody {
  code?: string;
  message?: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new ApiError(
      body.message ?? `HTTP ${response.status}`,
      body.code ?? "HTTP_ERROR",
      body.details,
    );
  }
  return response.json() as Promise<T>;
}

export const api = {
  config: () => request<PublicConfig>("/config"),
  testConnection: async () => {
    const result = await request<{ success: boolean; capabilities: Capabilities }>(
      "/connection/test",
      { method: "POST" },
    );
    return result.capabilities;
  },
  scanStatus: () => request<ScanStatus>("/scan/status"),
  scanSummary: async () => {
    const result = await request<{ available: boolean; summary: ScanSummary | null }>(
      "/scan/summary",
    );
    return result.summary;
  },
  startScan: (schemas: string[]) => request<{ accepted: boolean }>("/scan", {
    method: "POST",
    body: JSON.stringify({ schemas }),
  }),
  cancelScan: () => request<{ accepted: boolean }>("/scan/cancel", { method: "POST" }),
  searchObjects: (parameters: {
    q?: string;
    owner?: string;
    objectType?: string;
    pageSize?: number;
  }) => {
    const query = new URLSearchParams();
    Object.entries(parameters).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return request<ObjectSearchResult>(`/objects?${query}`);
  },
  subgraph: (payload: {
    rootObjectIds: string[];
    depth: number;
    direction: "INCOMING" | "OUTGOING" | "BOTH";
  }) => request<SubgraphResult>("/subgraph", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  impact: (payload: {
    objectId: string;
    mode: "DEPENDENTS" | "DEPENDENCIES";
    maxDepth?: number;
  }) => request<SubgraphResult>("/impact", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  paths: (payload: {
    sourceId: string;
    targetId: string;
    mode: "HOPS" | "WEIGHTED";
    directed: boolean;
    maxPaths: number;
  }) => request<PathResult>("/paths", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  analyses: async () => {
    const result = await request<{ items?: AnalysisRun[] }>("/analyses");
    return result.items ?? [];
  },
  startAnalysis: (payload: {
    name: string;
    objective: "CPM" | "MODULARITY";
    resolution: number;
    seed: number;
    minimumConfidence: number;
    hubPolicy: "NONE" | "DEGREE_NORMALIZATION" | "EXCLUDE_TOP_HUBS";
    includeTechnicalObjects: boolean;
  }) => request<{ accepted: boolean; analysisId: string }>("/analyses", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  startResolutionProfile: (payload: {
    name: string;
    objective: "CPM" | "MODULARITY";
    seed: number;
    minimumConfidence: number;
    hubPolicy: "NONE" | "DEGREE_NORMALIZATION" | "EXCLUDE_TOP_HUBS";
    includeTechnicalObjects: boolean;
  }) => request<{ accepted: boolean; analysisIds: string[] }>(
    "/analyses/resolution-profile",
    { method: "POST", body: JSON.stringify(payload) },
  ),
  startSeedProfile: (payload: {
    name: string;
    objective: "CPM" | "MODULARITY";
    resolution: number;
    minimumConfidence: number;
    hubPolicy: "NONE" | "DEGREE_NORMALIZATION" | "EXCLUDE_TOP_HUBS";
    includeTechnicalObjects: boolean;
  }) => request<{ accepted: boolean; analysisIds: string[]; baselineAnalysisId: string }>(
    "/analyses/seed-profile",
    { method: "POST", body: JSON.stringify(payload) },
  ),
  compareAnalyses: (analysisIds: string[]) => request<AnalysisComparison>(
    "/analyses/compare",
    { method: "POST", body: JSON.stringify({ analysisIds }) },
  ),
  cancelAnalysis: (analysisId: string) => request<{ accepted: boolean }>(
    `/analyses/${analysisId}/cancel`, { method: "POST" },
  ),
  deleteAnalysis: (analysisId: string) => request<{ deleted: boolean }>(
    `/analyses/${analysisId}`, { method: "DELETE" },
  ),
  communities: async (analysisId: string) => {
    const result = await request<{ items: CommunityMetrics[] }>(
      `/analyses/${analysisId}/communities`,
    );
    return result.items;
  },
  community: (analysisId: string, communityId: number) => request<CommunityDetail>(
    `/analyses/${analysisId}/communities/${communityId}`,
  ),
  communityGraph: (analysisId: string) => request<CommunityGraph>(
    `/analyses/${analysisId}/community-graph`,
  ),
  saveAnnotation: (payload: {
    analysisId: string;
    communityId: number;
    name: string | null;
    note: string | null;
  }) => request<Annotation>("/annotations", {
    method: "POST",
    body: JSON.stringify(payload),
  }),
  startExport: (analysisId: string, format: ExportJob["format"]) => request<{
    accepted: boolean;
    exportId: string;
  }>("/export", {
    method: "POST",
    body: JSON.stringify({ analysisId, format }),
  }),
  exportStatus: (exportId: string) => request<ExportJob>(`/export/${exportId}/status`),
};
