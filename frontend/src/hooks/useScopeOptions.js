import { useApiResource } from './useApiResource';
import { getFacilities, getDepartments } from '../api/client';

export function useScopeOptions() {
  const facilities  = useApiResource(() => getFacilities(), []);
  const departments = useApiResource(() => getDepartments(), []);
  return {
    facilities: facilities.data?.facilities ?? [],
    departments: departments.data?.departments ?? [],
    loading: facilities.loading || departments.loading,
  };
}