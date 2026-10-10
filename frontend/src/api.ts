/// <reference types="vite/client" />

const getApiBaseUrl = () => import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, '') || '';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const api = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const baseUrl = getApiBaseUrl();
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  const responseText = await response.text();
  let body: unknown;
  let parsedJson = false;
  try {
    body = responseText ? JSON.parse(responseText) : null;
    parsedJson = true;
  } catch {
    body = undefined;
  }

  if (!response.ok) {
    const detail = isRecord(body) ? body.detail : undefined;
    if (typeof detail === 'string') throw new Error(detail);
    if (detail !== undefined) throw new Error(JSON.stringify(detail));
    if (parsedJson && body !== null) throw new Error(JSON.stringify(body));
    throw new Error(
      `API request failed with HTTP ${response.status} and a non-JSON response for ${path}. ` +
      `Check that VITE_API_BASE_URL points to the FastAPI backend (currently ${baseUrl || 'unset'}).`,
    );
  }

  if (!parsedJson || body === null) {
    throw new Error(
      `Expected a JSON API response for ${path}, but received non-JSON content (HTTP ${response.status}). ` +
      `Check that VITE_API_BASE_URL points to the FastAPI backend (currently ${baseUrl || 'unset'}).`,
    );
  }
  return body as T;
};
