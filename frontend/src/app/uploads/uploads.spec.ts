import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { Auth } from '../core/auth';
import { Me, UploadRecord } from '../core/models';
import { UploadsPage } from './uploads';

const ADMIN: Me = {
  id: 1,
  username: 'admin',
  full_name: 'Summer Smith',
  role: 'admin',
  branch_id: null,
  branch: null,
  must_change_password: false,
};
const MANAGER: Me = {
  ...ADMIN,
  id: 7,
  username: 'manager.haifa',
  role: 'branch_manager',
  branch_id: 3,
  branch: 'Haifa',
};

const ROW: UploadRecord = {
  id: 42,
  logger: 'TL-0232',
  branch: 'Haifa',
  original_filename: 'TL-0232_2026-W39.csv',
  sha256: 'x',
  row_count: 96,
  error_count: 0,
  status: 'flagged_mistake',
  started_at: '2026-11-11T17:21:00',
  finished_at: null,
  note: null,
  uploaded_by_id: 7,
  uploaded_by: 'Haifa manager',
  flag_reason: 'Uploaded twice by mistake',
  flagged_by: 'Haifa manager',
  flagged_at: '2026-11-11T17:22:00',
  void_reason: null,
  voided_by: null,
  voided_at: null,
};

/** Clicks the real buttons, so a broken (click) binding fails here, not on a phone. */
describe('UploadsPage actions', () => {
  let fixture: ComponentFixture<UploadsPage>;
  let http: HttpTestingController;
  let open: ReturnType<typeof vi.fn>;

  async function render(
    me: Me,
    row: UploadRecord,
    reason: string | null = 'Duplicate, voided after review',
  ) {
    // A cancelled dialog closes with undefined.
    open = vi.fn().mockReturnValue({ afterClosed: () => of(reason ?? undefined) });
    TestBed.configureTestingModule({
      imports: [UploadsPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: MatDialog, useValue: { open } },
      ],
    });
    TestBed.inject(Auth).user.set(me);
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(UploadsPage);
    await fixture.whenStable();
    http.expectOne((r) => r.url === '/api/uploads').flush([row]);
    await fixture.whenStable();
  }

  const button = (id: string) =>
    fixture.nativeElement.querySelector(`[data-testid="${id}"]`) as HTMLButtonElement | null;

  it('Void opens the reason dialog and posts the void', async () => {
    await render(ADMIN, ROW);
    button('void')!.click();
    expect(open).toHaveBeenCalledTimes(1);
    const req = http.expectOne('/api/uploads/42/void');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ reason: 'Duplicate, voided after review' });
  });

  it('Dismiss flag posts straight away', async () => {
    await render(ADMIN, ROW);
    button('dismiss')!.click();
    expect(http.expectOne('/api/uploads/42/dismiss-flag').request.method).toBe('POST');
  });

  it('a manager flags their own active upload with a reason, and has no Void', async () => {
    await render(MANAGER, { ...ROW, status: 'active', flag_reason: null }, 'Wrong week');
    expect(button('void')).toBeNull();
    button('flag')!.click();
    expect(open).toHaveBeenCalledTimes(1);
    expect(http.expectOne('/api/uploads/42/flag').request.body).toEqual({ reason: 'Wrong week' });
  });

  it('cancelling the dialog sends nothing', async () => {
    await render(ADMIN, ROW, null);
    button('void')!.click();
    http.expectNone('/api/uploads/42/void');
  });
});
