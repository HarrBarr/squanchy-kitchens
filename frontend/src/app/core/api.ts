import { HttpClient, HttpErrorResponse, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import {
  AssignmentIn,
  AuditEntry,
  Branch,
  Dashboard,
  ImportSummary,
  LoggerInfo,
  Me,
  PasswordReset,
  Period,
  Report,
  Series,
  TokenResponse,
  UploadRecord,
  UploadStatus,
  UserCreate,
  UserPatch,
  UserRow,
} from './models';

function params(obj: Record<string, string | number | null | undefined>): HttpParams {
  let p = new HttpParams();
  for (const [k, v] of Object.entries(obj)) {
    if (v !== null && v !== undefined && v !== '') p = p.set(k, String(v));
  }
  return p;
}

/** Human-readable message from an API error (FastAPI puts it in `detail`). */
export function errorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
      return detail.message;
    }
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

  uploads(
    filter: { status?: UploadStatus | null; logger?: string | null } = {},
  ): Observable<UploadRecord[]> {
    return this.http.get<UploadRecord[]>('/api/uploads', { params: params(filter) });
  }

  pendingReview(): Observable<UploadRecord[]> {
    return this.http.get<UploadRecord[]>('/api/uploads/pending-review');
  }

  pendingReviewCount(): Observable<number> {
    return this.http
      .get<{ count: number }>('/api/uploads/pending-review/count')
      .pipe(map((r) => r.count));
  }

  flagUpload(id: number, reason: string): Observable<UploadRecord> {
    return this.http.post<UploadRecord>(`/api/uploads/${id}/flag`, { reason });
  }

  dismissFlag(id: number): Observable<UploadRecord> {
    return this.http.post<UploadRecord>(`/api/uploads/${id}/dismiss-flag`, {});
  }

  voidUpload(id: number, reason: string): Observable<UploadRecord> {
    return this.http.post<UploadRecord>(`/api/uploads/${id}/void`, { reason });
  }

  /** The CSV needs the Bearer token, so it is fetched as a blob, not followed as a link. */
  downloadReportCsv(
    period: Period,
    branch?: string | null,
    fridge?: number | null,
  ): Observable<{
    blob: Blob;
    filename: string;
  }> {
    return this.http
      .get('/api/report.csv', {
        params: params({ from: period.from, to: period.to, branch, fridge }),
        responseType: 'blob',
        observe: 'response',
      })
      .pipe(
        map((r: HttpResponse<Blob>) => ({
          blob: r.body ?? new Blob(),
          filename:
            /filename="([^"]+)"/.exec(r.headers.get('content-disposition') ?? '')?.[1] ??
            'squanchy-excursions.csv',
        })),
      );
  }

  // ---- auth ----

  login(username: string, password: string): Observable<TokenResponse> {
    const body = new HttpParams().set('username', username).set('password', password);
    return this.http.post<TokenResponse>('/api/auth/login', body);
  }

  me(): Observable<Me> {
    return this.http.get<Me>('/api/auth/me');
  }

  changePassword(currentPassword: string, newPassword: string): Observable<Me> {
    return this.http.post<Me>('/api/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }

  // ---- users (admin) ----

  users(): Observable<UserRow[]> {
    return this.http.get<UserRow[]>('/api/users');
  }

  createUser(body: UserCreate): Observable<UserRow> {
    return this.http.post<UserRow>('/api/users', body);
  }

  updateUser(id: number, body: UserPatch): Observable<UserRow> {
    return this.http.patch<UserRow>(`/api/users/${id}`, body);
  }

  resetPassword(id: number): Observable<PasswordReset> {
    return this.http.post<PasswordReset>(`/api/users/${id}/reset-password`, {});
  }

  auditLog(
    filter: { action?: string | null; user?: string | null } = {},
  ): Observable<AuditEntry[]> {
    return this.http.get<AuditEntry[]>('/api/audit-log', { params: params(filter) });
  }
}

/** Save a blob as a file in the browser. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
