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
};
