import { useApiResource } from './useApiResource';
import { getTopEvents } from '../api/client';
import { REFRESH_MS } from '../config/constants';

export function useTopEvents(scope, limit = 5) {
  return useApiResource(
    () => getTopEvents(scope, limit),
    [scope.view, scope.facilityId, scope.departmentId, limit],
    { intervalMs: REFRESH_MS }
  );
}