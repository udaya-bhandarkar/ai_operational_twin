import { API_BASE, USE_MOCKS } from '../config/constants';
import * as mock from '../mocks/mockData';

async function request(path, options = {}) {
  if (USE_MOCKS) return mock.respond(path, options);

  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).error ?? ''; } catch { /* ignore */ }
    throw new Error(`Request ${path} failed (${res.status}). ${detail}`);
  }
  return res.json();
}

export const getKpis           = (view)           => request(`/kpis?view=${encodeURIComponent(view)}`);
export const getWasteOverTime  = (view, r = '24h')=> request(`/waste-over-time?view=${view}&range=${r}`);
export const getWasteByMachine = (view)           => request(`/waste-by-machine?view=${view}`);
export const getTopEvents      = (limit = 5)      => request(`/top-events?limit=${limit}`);
export const getMachines       = (view)           => request(`/machines?view=${view}`);

export const sendChatMessage = ({ message, threadId, view }) =>
  request('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, thread_id: threadId, view }),
  });