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
};
