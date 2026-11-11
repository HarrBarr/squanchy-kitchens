import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  AssignmentIn,
  Branch,
  Dashboard,
  ImportSummary,
  LoggerInfo,
  Period,
  Report,
  Series,
  UploadRecord,
} from './models';

function params(obj: Record<string, string | number | null | undefined>): HttpParams {
  let p = new HttpParams();
  for (const [k, v] of Object.entries(obj)) {
    if (v !== null && v !== undefined && v !== '') p = p.set(k, String(v));
  }
  return p;
}

/** The query string the CSV link uses, so it matches the on-screen report exactly. */
export function reportCsvUrl(
  period: Period,
  branch?: string | null,
  fridge?: number | null,
): string {
  const q = params({ from: period.from, to: period.to, branch, fridge }).toString();
  return `/api/report.csv${q ? '?' + q : ''}`;
}

/** Human-readable message from an API error (FastAPI puts it in `detail`). */
export function errorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return detail.map((d) => d.msg).join('; ');
    if (err.status === 0) return 'Cannot reach the server. Is the API running?';
    return `${err.status} ${err.statusText}`;
  }
  return String(err);
}

@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);

  dashboard(period: Period, branch?: string | null): Observable<Dashboard> {
    return this.http.get<Dashboard>('/api/dashboard', {
      params: params({ from: period.from, to: period.to, branch }),
    });
  }

  series(fridgeId: number, period: Period): Observable<Series> {
    return this.http.get<Series>(`/api/fridges/${fridgeId}/series`, {
      params: params({ from: period.from, to: period.to }),
    });
  }

  report(period: Period, branch?: string | null): Observable<Report> {
    return this.http.get<Report>('/api/report', {
      params: params({ from: period.from, to: period.to, branch }),
    });
  }

  branches(): Observable<Branch[]> {
    return this.http.get<Branch[]>('/api/branches');
  }

  loggers(): Observable<LoggerInfo[]> {
    return this.http.get<LoggerInfo[]>('/api/loggers');
  }

  addAssignment(code: string, body: AssignmentIn): Observable<LoggerInfo> {
    return this.http.post<LoggerInfo>(`/api/loggers/${encodeURIComponent(code)}/assignments`, body);
  }

  upload(file: File, loggerCode: string): Observable<ImportSummary> {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('logger_id', loggerCode);
    return this.http.post<ImportSummary>('/api/uploads', form);
  }

  uploads(): Observable<UploadRecord[]> {
    return this.http.get<UploadRecord[]>('/api/uploads');
  }
}
