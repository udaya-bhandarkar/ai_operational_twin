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

function scopeParams({ view, facilityId, departmentId }) {
  const params = new URLSearchParams({ view });
  if (facilityId) params.set('facility_id', facilityId);
  if (departmentId) params.set('department_id', departmentId);
  return params.toString();
}

export const getKpis           = (scope)          => request(`/kpis?${scopeParams(scope)}`);
export const getWasteOverTime  = (scope, r = '24h')=> request(`/waste-over-time?${scopeParams(scope)}&range=${r}`);
export const getWasteByMachine = (scope)          => request(`/waste-by-machine?${scopeParams(scope)}`);
export const getTopEvents      = (scope, limit = 5)=> request(`/top-events?${scopeParams(scope)}&limit=${limit}`);
export const getMachines       = (scope)          => request(`/machines?${scopeParams(scope)}`);
export const getFacilities  = () => request('/facilities');
export const getDepartments = () => request('/departments');
export const sendChatMessage = ({ message, threadId, view }) =>
  request('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, thread_id: threadId, view }),
  });