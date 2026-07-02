import { useApiResource } from './useApiResource';
import { getWasteByMachine } from '../api/client';
import { REFRESH_MS } from '../config/constants';

export function useWasteByMachine(view) {
  return useApiResource(() => getWasteByMachine(view), [view], { intervalMs: REFRESH_MS });
}