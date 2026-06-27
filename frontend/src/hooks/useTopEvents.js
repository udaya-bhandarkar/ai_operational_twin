import { useApiResource } from './useApiResource';
import { getTopEvents } from '../api/client';
import { REFRESH_MS } from '../config/constants';

export function useTopEvents(limit = 5) {
  return useApiResource(() => getTopEvents(limit), [limit], { intervalMs: REFRESH_MS });
}