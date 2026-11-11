import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { TestbedHarnessEnvironment } from '@angular/cdk/testing/testbed';
import { MatTooltipHarness } from '@angular/material/tooltip/testing';
import { routes } from './app.routes';

/** Smoke test: each screen renders its empty state with an empty backend. */
describe('routes', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  const period = {
    period_from: '2026-09-14',
    period_to: '2026-09-20',
    period_label: '2026-W38',
    threshold_c: 5,
  };

  async function render(url: string, responses: Record<string, object>): Promise<string> {
    return (await renderHarness(url, responses)).routeNativeElement?.textContent ?? '';
  }

  async function renderHarness(
    url: string,
    responses: Record<string, object>,
  ): Promise<RouterTestingHarness> {
    const harness = await RouterTestingHarness.create();
    await harness.navigateByUrl(url);
    await harness.fixture.whenStable();
    for (const [path, body] of Object.entries(responses)) {
      http.expectOne((r) => r.url === path).flush(body);
    }
    await harness.fixture.whenStable();
    http.verify();
    return harness;
  }

  it('dashboard: no fridges yet', async () => {
    const text = await render('/', {
      '/api/branches': [],
      '/api/dashboard': { ...period, counts: { red: 0, amber: 0, green: 0, grey: 0 }, fridges: [] },
    });
    expect(text).toContain('No fridges yet');
  });

  it('report: no excursions', async () => {
    const text = await render('/report', {
      '/api/branches': [],
      '/api/report': { ...period, timezone: 'Asia/Jerusalem', rows: [] },
    });
    expect(text).toContain('No excursions above 5°C');
  });

  it('registry: no uploads', async () => {
    const text = await render('/registry', { '/api/loggers': [], '/api/uploads': [] });
    expect(text).toContain('No files uploaded yet');
  });

  it('dashboard: says the week is incomplete when only some fridges reported', async () => {
    const card = (branch: string, colour: string, awaiting: boolean) => ({
      fridge_id: branch.length,
      branch,
      fridge: 'Dairy',
      loggers: [],
      colour,
      ongoing: false,
      awaiting_upload: awaiting,
      still_above: false,
      still_above_note: null,
      last_seen_local: '2026-09-20T23:45:00',
      reason: awaiting ? "Awaiting this week's file · last reading Sun 20 Sep 23:45" : 'OK',
      last_temp_c: awaiting ? null : 3.5,
      last_reading_local: awaiting ? null : '2026-09-27T23:45:00',
      excursion_count: 0,
      gap_count: 0,
      error_count: 0,
      spike_count: 0,
      peak_c: null,
    });
    const text = await render('/', {
      '/api/branches': [],
      '/api/dashboard': {
        ...period,
        period_from: '2026-09-21',
        period_to: '2026-09-27',
        period_label: '2026-W39',
        counts: { red: 0, amber: 0, green: 1, grey: 1 },
        fridges_total: 2,
        fridges_with_readings: 1,
        previous_period_from: '2026-09-14',
        previous_period_to: '2026-09-20',
        previous_period_label: '2026-W38',
        fridges: [card('Haifa', 'green', false), card('Netanya', 'grey', true)],
      },
    });
    expect(text).toContain('2026-W39 is incomplete');
    expect(text).toContain('1 of 2 fridges have readings so far');
    expect(text).toContain('See 2026-W38');
    expect(text).toContain('Awaiting upload');
    expect(text).not.toContain('No readings in this period');
  });

  it('dashboard: a fridge still above 5°C at its last upload stays red, with a hover note', async () => {
    const rishon = {
      fridge_id: 7,
      branch: 'Rishon LeZion',
      fridge: 'Cream cakes',
      loggers: ['TL-0388'],
      colour: 'red',
      ongoing: true,
      awaiting_upload: true,
      still_above: true,
      still_above_note: 'still above 5°C at last reading, Sun 20 Sep 23:45',
      last_seen_local: '2026-09-20T23:45:00',
      reason: "Ongoing 11.5°C peak since Mon 14 Sep 06:15 · awaiting this week's file",
      last_temp_c: 11.2,
      last_reading_local: null,
      excursion_count: 0,
      gap_count: 0,
      error_count: 0,
      spike_count: 0,
      peak_c: 11.5,
    };
    const harness = await renderHarness('/', {
      '/api/branches': [],
      '/api/dashboard': {
        ...period,
        period_from: '2026-09-21',
        period_to: '2026-09-27',
        period_label: '2026-W39',
        counts: { red: 1, amber: 0, green: 0, grey: 0 },
        fridges_total: 1,
        fridges_with_readings: 0,
        previous_period_from: '2026-09-14',
        previous_period_to: '2026-09-20',
        previous_period_label: '2026-W38',
        fridges: [rishon],
      },
    });
    const el = harness.routeNativeElement!;
    expect(el.querySelector('.card')!.classList).toContain('red');
    expect(el.querySelector('.ongoing')?.textContent).toContain('Ongoing');
    expect(el.textContent).toContain('Last uploaded reading Sun 20 Sep 23:45');

    const loader = TestbedHarnessEnvironment.loader(harness.fixture);
    const tooltip = await loader.getHarness(MatTooltipHarness);
    expect(await (await tooltip.host()).text()).toBe('Above 5°C');
    await tooltip.show();
    expect(await tooltip.getTooltipText()).toBe(
      'still above 5°C at last reading, Sun 20 Sep 23:45',
    );
  });
});
