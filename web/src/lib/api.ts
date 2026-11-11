/** The only module that talks to the API. Errors carry what the UI needs to explain them. */

export type RefusalReason =
  | "no_sources"
  | "insufficient_evidence"
  | "unverified"
  | "truncated"
  | "budget_exhausted"
  | "budget_unavailable"
  | "model_unavailable"
  | "duplicate_request";

export interface Quote {
  marker: number | null;
  text: string;
  start: number | null;
  end: number | null;
}

export interface Source {
  n: number;
  title: string;
  heading: string;
  edition: string;
  url: string;
  cited: boolean;
  quotes: Quote[];
}

export interface Redaction {
  kind: string;
  count: number;
}

export interface Refusal {
  reason: RefusalReason;
  message: string;
  details: string[];
}

export interface AnswerResponse {
  request_id: string;
  answer: string | null;
  refusal: Refusal | null;
  sources: Source[];
  redactions: Redaction[];
}

export interface Session {
  tenant_id: string;
  user_id: string;
  role: string;
}

export type ApiFailureKind = "unauthorised" | "too_many" | "unavailable" | "invalid" | "network" | "unknown";

export class ApiError extends Error {
  readonly kind: ApiFailureKind;
  readonly retryAfterSeconds: number | null;
  readonly status: number | null;

  constructor(kind: ApiFailureKind, message: string, retryAfterSeconds: number | null = null, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.retryAfterSeconds = retryAfterSeconds;
    this.status = status;
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "";

function retryAfter(response: Response): number | null {
  const header = response.headers.get("retry-after");
  if (!header) return null;
  const seconds = Number.parseInt(header, 10);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        "content-type": "application/json",
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("network", "We could not reach Firebrief.");
  }

  if (response.status === 401) {
    throw new ApiError("unauthorised", "Your session ended.", null, 401);
  }
  if (response.status === 429) {
    throw new ApiError("too_many", "Too many requests.", retryAfter(response), 429);
  }
  if (response.status === 503) {
    throw new ApiError("unavailable", "Firebrief is temporarily unavailable.", retryAfter(response), 503);
  }
  if (response.status === 400 || response.status === 403) {
    throw new ApiError("invalid", "That request could not be completed.", null, response.status);
  }
  if (!response.ok) {
    throw new ApiError("unknown", "Something went wrong.", null, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  requestMagicLink: (tenantId: string, email: string) =>
    request<{ status: string }>("/v1/auth/magic-link", {
      method: "POST",
      body: JSON.stringify({ tenant_id: tenantId, email }),
    }),

  verify: (token: string) =>
    request<Session>("/v1/auth/verify", { method: "POST", body: JSON.stringify({ token }) }),

  me: () => request<Session>("/v1/auth/me"),

  logout: () => request<void>("/v1/auth/logout", { method: "POST" }),

  ask: (question: string) =>
    request<AnswerResponse>("/v1/answers", { method: "POST", body: JSON.stringify({ question }) }),
};
