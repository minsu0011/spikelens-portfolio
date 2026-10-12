export class ApiError extends Error {
  constructor(message: string, public status: number, public code: string, public requestId?: string, public details?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

function csrfToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie.split(";").map((cookie) => cookie.trim()).find((cookie) => cookie.startsWith("spikelens_csrf="))?.split("=").slice(1).join("=");
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes((options.method ?? "GET").toUpperCase());
  const csrf = csrfToken();
  if (unsafe && csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new ApiError("서버에 연결할 수 없습니다. 연결을 확인하고 다시 시도하세요.", 0, "NETWORK_ERROR");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = body?.error?.message ?? (response.status === 401 ? "로그인이 필요하거나 세션이 만료되었습니다." : response.status === 403 ? "이 작업에 대한 권한이 없습니다." : response.status === 404 ? "요청한 데이터를 찾을 수 없습니다." : "요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.");
    throw new ApiError(message, response.status, body?.error?.code ?? "HTTP_ERROR", body?.request_id, body?.error?.details);
  }
  return body as T;
}

export function queryString(values: Record<string, string | number | undefined>): string {
  const result = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== "") result.set(key, String(value)); });
  return result.toString();
}
