const configuredBase = import.meta.env.VITE_API_URL?.replace(/\/$/, "");
export const API_BASE = configuredBase || `${window.location.protocol}//${window.location.hostname}:8080`;
export const KIOSK_ID = import.meta.env.VITE_KIOSK_ID || "kiosk-local";

export async function apiFetch(path, options = {}, timeoutMs = 65000) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(new DOMException("Request timed out", "TimeoutError")), timeoutMs);
  const externalSignal = options.signal;
  const abortFromExternal = () => controller.abort(externalSignal.reason);
  if (externalSignal) {
    if (externalSignal.aborted) abortFromExternal();
    else externalSignal.addEventListener("abort", abortFromExternal, { once: true });
  }
  try {
    return await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...(options.headers || {}), "X-Kiosk-ID": KIOSK_ID },
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
    externalSignal?.removeEventListener("abort", abortFromExternal);
  }
}

export function patientHeaders(sessionId, sessionToken, json = false) {
  const headers = {
    "X-Session-Id": sessionId,
    "X-Session-Token": sessionToken,
  };
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

export function staffHeaders(staffToken, json = false) {
  const headers = { "X-Staff-Token": staffToken };
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}
