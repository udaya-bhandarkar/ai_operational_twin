export const API_BASE  = import.meta.env.VITE_API_BASE ?? '/api';
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';
export const REFRESH_MS = Number(import.meta.env.VITE_REFRESH_MS ?? 3_600_000); // 1 hour

export const VIEWS = [
  { id: 'ceo',        label: 'CEO' },
  { id: 'factory',    label: 'Factory Manager' },
  { id: 'department', label: 'Department Manager' },
];

export const COLORS = {
  primary: 'rgb(19, 140, 143)',
  deep:    'rgb(0, 90, 112)',
  accent:  'rgb(0, 122, 140)',
  danger:  '#c0392b',
  series:  ['rgb(0, 122, 140)', 'rgb(19, 140, 143)', 'rgb(0, 90, 112)'],
};