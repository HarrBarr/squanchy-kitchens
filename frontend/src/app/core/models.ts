export type Colour = 'red' | 'amber' | 'green' | 'grey';

export interface FridgeCard {
  fridge_id: number;
  branch: string;
  fridge: string;
  loggers: string[];
  colour: Colour;
  ongoing: boolean;
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

export interface UploadRecord {
  id: number;
  logger: string;
  original_filename: string;
  sha256: string;
  row_count: number;
  error_count: number;
  status: string;
  started_at: string;
  finished_at: string | null;
  note: string | null;
}

export interface Period {
  from?: string | null;
  to?: string | null;
}
