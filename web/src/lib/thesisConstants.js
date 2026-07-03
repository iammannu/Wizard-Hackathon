// Shared Living Thesis vocabulary — lifecycle stages, version change types, and
// claim statuses all mirror the string enums defined in app/models/thesis.py.
// Single source so WorkspaceDetail's full panel and the Workspaces list badge
// render the same icon/color/label for the same backend value.

export const LIFECYCLE_META = {
  forming:     { label: 'Forming',     icon: '🌱', color: 'var(--accent2)' },
  established: { label: 'Established', icon: '✓',  color: 'var(--bull)' },
  evolving:    { label: 'Evolving',    icon: '↻',  color: 'var(--warn)' },
  challenged:  { label: 'Challenged',  icon: '⚠',  color: 'var(--warn)' },
  invalidated: { label: 'Invalidated', icon: '✕',  color: 'var(--bear)' },
}

export const CHANGE_TYPE_META = {
  reinforced:  { label: 'Reinforced',  color: 'var(--bull)' },
  evolved:     { label: 'Evolved',     color: 'var(--accent2)' },
  challenged:  { label: 'Challenged',  color: 'var(--warn)' },
  invalidated: { label: 'Invalidated', color: 'var(--bear)' },
}

export const CLAIM_STATUS_META = {
  confirmed:    { label: 'Confirmed',    color: 'var(--bull)' },
  strengthened: { label: 'Strengthened', color: 'var(--accent2)' },
  active:       { label: 'Active',       color: 'var(--muted)' },
  weakened:     { label: 'Weakened',     color: 'var(--warn)' },
  refuted:      { label: 'Refuted',      color: 'var(--bear)' },
}
