import { useApiResource } from './useApiResource';
import { getWasteByMachine } from '../api/client';
import { REFRESH_MS } from '../config/constants';

export function useWasteByMachine(scope) {
  return useApiResource(
    () => getWasteByMachine(scope),
    [scope.view, scope.facilityId, scope.departmentId],
    { intervalMs: REFRESH_MS }
  );
}