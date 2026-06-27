import { useApiResource } from './useApiResource';
import { getKpis } from '../api/client';
import { REFRESH_MS } from '../config/constants';

export function useKpis(view) {
  return useApiResource(() => getKpis(view), [view], { intervalMs: REFRESH_MS });
}