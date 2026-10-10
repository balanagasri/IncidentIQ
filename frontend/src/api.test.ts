import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('API client', () => {
  it('uses the configured backend origin and preserves backend API paths', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://incidentiq-vzw6.onrender.com/');
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"status":"ok"}', {
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(api('/api/health')).resolves.toEqual({ status: 'ok' });
    expect(fetchMock).toHaveBeenCalledWith('https://incidentiq-vzw6.onrender.com/api/health', expect.any(Object));
  });

  it('turns an HTML 404 into a useful error instead of a JSON parse exception', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://incidentiq-vzw6.onrender.com');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html><title>Not Found</title></html>', {
      status: 404,
      headers: { 'Content-Type': 'text/html' },
    })));

    await expect(api('/api/incidents')).rejects.toThrow(
      /HTTP 404 and a non-JSON response for \/api\/incidents.*VITE_API_BASE_URL.*https:\/\/incidentiq-vzw6\.onrender\.com/,
    );
  });

  it('keeps FastAPI JSON detail errors readable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"Incident not found"}', {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    })));

    await expect(api('/api/incidents/missing')).rejects.toThrow('Incident not found');
  });
});
