export type Colour = 'red' | 'amber' | 'green' | 'grey';

export interface FridgeCard {
  fridge_id: number;
  branch: string;
  fridge: string;
  loggers: string[];
  colour: Colour;
  ongoing: boolean;
  /** Has older readings, but this period's file has not been uploaded yet. */
  awaiting_upload: boolean;
  /** Still above the limit at its last uploaded reading (from an earlier period) and no
   *  newer file has shown it recover: stays red. */
  still_above: boolean;
  /** Hover text for the card label, e.g. "still above 5°C at last reading, Sun 20 Sep 23:45". */
  still_above_note: string | null;
  last_seen_local: string | null;
  reason: string;
  last_temp_c: number | null;
  last_reading_local: string | null;
  excursion_count: number;
  gap_count: number;
  error_count: number;
  spike_count: number;
  peak_c: number | null;
}

export interface Dashboard {
  period_from: string;
  period_to: string;
  period_label: string;
  threshold_c: number;
  counts: Record<Colour, number>;
  fridges_total: number;
  fridges_with_readings: number;
  previous_period_from: string | null;
  previous_period_to: string | null;
  previous_period_label: string | null;
  scope_branch: string | null;
  branches: BranchStatus[];
  fridges: FridgeCard[];
}

export interface SeriesPoint {
  ts_local: string;
  temp_c: number | null;
  status: 'ok' | 'err';
  raw_value: string;
  logger: string;
}

export interface Span {
  start_local: string;
  end_local: string;
  duration_minutes: number;
  logger: string;
}

export interface ExcursionSpan extends Span {
  peak_c: number;
  n_readings: number;
  is_open: boolean;
}

export interface SpikePoint {
  ts_local: string;
  temp_c: number;
  logger: string;
}

export interface Series {
  fridge_id: number;
  branch: string;
  fridge: string;
  period_from: string;
  period_to: string;
  period_label: string;
  threshold_c: number;
  sample_interval_minutes: number;
  readings: SeriesPoint[];
  gaps: Span[];
  excursions: ExcursionSpan[];
  spikes: SpikePoint[];
}

export interface ReportRow {
  id: number;
  branch: string;
  fridge: string;
  fridge_id: number;
  logger: string;
  start_local: string;
  end_local: string;
  duration_minutes: number;
  duration_label: string;
  peak_c: number;
  n_readings: number;
  is_open: boolean;
}

export interface Report {
  period_from: string;
  period_to: string;
  period_label: string;
  timezone: string;
  threshold_c: number;
  rows: ReportRow[];
}

export interface Assignment {
  id: number;
  branch: string;
  fridge: string;
  fridge_id: number;
  unit: 'C' | 'F';
  assigned_from: string;
  assigned_to: string | null;
}

export interface LoggerInfo {
  logger_code: string;
  current: Assignment | null;
  assignments: Assignment[];
}

export interface AssignmentIn {
  branch: string;
  fridge: string;
  unit: 'C' | 'F';
  assigned_from: string;
  assigned_to?: string | null;
}

export interface Branch {
  id: number;
  name: string;
  fridge_count: number;
}

export interface ImportSummary {
  logger: string;
  filename: string;
  sha256: string;
  already_imported: boolean;
  upload_id: number | null;
  rows_in_file: number;
  inserted: number;
  updated: number;
  unchanged: number;
  duplicates: number;
  sensor_errors: number;
  rejected_lines: number;
  unassigned_rows: number;
  excursions: number;
  spikes: number;
  gaps: number;
  first_reading_local: string | null;
  last_reading_local: string | null;
  warnings: string[];
}

export type UploadStatus = 'active' | 'flagged_mistake' | 'voided';

export interface UploadRecord {
  id: number;
  logger: string;
  branch: string | null;
  original_filename: string;
  sha256: string;
  row_count: number;
  error_count: number;
  status: UploadStatus;
  started_at: string;
  finished_at: string | null;
  note: string | null;
  uploaded_by_id: number | null;
  uploaded_by: string | null;
  flag_reason: string | null;
  flagged_by: string | null;
  flagged_at: string | null;
  void_reason: string | null;
  voided_by: string | null;
  voided_at: string | null;
}

export type Role = 'admin' | 'branch_manager';

export interface Me {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  branch_id: number | null;
  branch: string | null;
  must_change_password: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  must_change_password: boolean;
}

export interface UserRow {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  branch_id: number | null;
  branch: string | null;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}

export interface UserCreate {
  username: string;
  full_name: string;
  branch_id: number;
  password: string;
}

export interface UserPatch {
  full_name?: string;
  branch_id?: number;
  is_active?: boolean;
}

export interface PasswordReset {
  user: UserRow;
  temporary_password: string;
}

export interface AuditEntry {
  id: number;
  created_at: string;
  user: string | null;
  username: string | null;
  action: string;
  entity_type: string;
  entity_id: number | null;
  details: Record<string, unknown> | null;
}

export interface LastUpload {
  upload_id: number;
  uploaded_at: string;
  filename: string;
  logger: string;
  uploaded_by: string | null;
}

export interface BranchStatus {
  branch: string;
  last_upload: LastUpload | null;
  missing: boolean;
}

export interface Period {
  from?: string | null;
  to?: string | null;
}
