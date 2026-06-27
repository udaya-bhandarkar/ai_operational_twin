import { useApiResource } from './useApiResource';
import { getWasteOverTime } from '../api/client';
import { REFRESH_MS } from '../config/constants';

export function useWasteOverTime(view) {
  return useApiResource(() => getWasteOverTime(view), [view], { intervalMs: REFRESH_MS });
}