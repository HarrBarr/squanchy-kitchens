import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialogRef } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { LoggerInfo } from '../core/models';
import { UploadDialog } from './upload-dialog';

const LOGGERS: LoggerInfo[] = ['TL-0231', 'TL-0512'].map((code) => ({
  logger_code: code,
  current: {
    id: 1,
    branch: 'Jerusalem',
    fridge: 'Dairy',
    fridge_id: 1,
    unit: 'C',
    assigned_from: '2026-01-01',
    assigned_to: null,
  },
  assignments: [],
}));

describe('UploadDialog', () => {
  let fixture: ComponentFixture<UploadDialog>;
  let dialog: UploadDialog;
  let http: HttpTestingController;

  const submitButton = () =>
    fixture.nativeElement.querySelector('[data-testid="submit"]') as HTMLButtonElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [UploadDialog],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: MatDialogRef, useValue: { close: vi.fn() } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(UploadDialog);
    dialog = fixture.componentInstance;
    http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/loggers').flush(LOGGERS);
    await fixture.whenStable();
  });

  afterEach(() => http.verify());

  it('keeps Upload disabled until both a file and a logger are chosen', async () => {
    expect(submitButton().disabled).toBe(true);

    dialog.setFile(new File(['x'], 'fridge-export.csv'));
    await fixture.whenStable();
    expect(dialog.logger()).toBeNull(); // no code in the name, nothing guessed
    expect(submitButton().disabled).toBe(true);

    dialog.selectLogger('TL-0231');
    await fixture.whenStable();
    expect(submitButton().disabled).toBe(false);
  });

  it('pre-selects the logger from a filename like TL-0512_2026-W38.csv', async () => {
    dialog.setFile(new File(['x'], 'TL-0512_2026-W38.csv'));
    await fixture.whenStable();
    expect(dialog.logger()).toBe('TL-0512');
    expect(dialog.guessed()).toBe(true);
    expect(submitButton().disabled).toBe(false);
  });

  it('lets Summer override the guessed logger', async () => {
    dialog.setFile(new File(['x'], 'TL-0512_2026-W38.csv'));
    dialog.selectLogger('TL-0231');
    await fixture.whenStable();
    expect(dialog.logger()).toBe('TL-0231');
    expect(dialog.guessed()).toBe(false);
  });

  it('shows the 422 message for an unknown logger', async () => {
    dialog.setFile(new File(['x'], 'TL-0512_2026-W38.csv'));
    dialog.submit();
    http
      .expectOne('/api/uploads')
      .flush(
        { detail: 'Logger TL-0512 is not in the registry.' },
        { status: 422, statusText: 'Unprocessable' },
      );
    await fixture.whenStable();
    expect(fixture.nativeElement.textContent).toContain('is not in the registry');
  });
});
