import { useApiResource } from './useApiResource';
import { getKpis } from '../api/client';
import { REFRESH_MS } from '../config/constants';

export function useKpis(scope) {
  return useApiResource(
    () => getKpis(scope),
    [scope.view, scope.facilityId, scope.departmentId],
    { intervalMs: REFRESH_MS }
  );
}