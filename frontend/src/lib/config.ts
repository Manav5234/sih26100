/**
 * API URL configuration — single source of truth for API base URL resolution.
 *
 * Client components should use getApiUrl() (reads NEXT_PUBLIC_API_URL env var).
 * Server components should use getServerApiUrl() (reads internal API_URL env var).
 * Falls back to "http://localhost:8010" in both cases (backend uvicorn port).
 */
export function getApiUrl(): string {
  // Client: use NEXT_PUBLIC_API_URL (prefixed for Next.js client access)
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

export function getServerApiUrl(): string {
  // Server: check BACKEND_URL (Vercel service binding), API_URL, or NEXT_PUBLIC_API_URL fallback
  return (
    process.env.BACKEND_URL ||
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  );
}