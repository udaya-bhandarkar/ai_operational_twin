import { useApiResource } from './useApiResource';
import { getWasteOverTime } from '../api/client';
import { REFRESH_MS } from '../config/constants';

export function useWasteOverTime(scope) {
  return useApiResource(
    () => getWasteOverTime(scope),
    [scope.view, scope.facilityId, scope.departmentId],
    { intervalMs: REFRESH_MS }
  );
}