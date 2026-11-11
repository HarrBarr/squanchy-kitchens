import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  Router,
  RouterStateSnapshot,
  UrlTree,
  provideRouter,
} from '@angular/router';
import { App } from '../app';
import { uploadActions } from '../uploads/uploads';
import { Auth } from './auth';
import { authInterceptor } from './auth.interceptor';
import { adminGuard, authGuard } from './guards';
import { Me } from './models';

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
  id: 7,
  username: 'manager.rishon',
  full_name: 'Rishon LeZion manager',
  role: 'branch_manager',
  branch_id: 2,
  branch: 'Rishon LeZion',
  must_change_password: false,
};

function setup() {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(),
    ],
  });
  return {
    auth: TestBed.inject(Auth),
    http: TestBed.inject(HttpTestingController),
    router: TestBed.inject(Router),
  };
}

const runGuard = (guard: typeof authGuard, url: string) =>
  TestBed.runInInjectionContext(() =>
    guard({} as ActivatedRouteSnapshot, { url } as RouterStateSnapshot),
  );

describe('guards', () => {
  afterEach(() => localStorage.clear());

  it('authGuard sends a signed-out visitor to sign-in, keeping where they were going', () => {
    const { router } = setup();
    const result = runGuard(authGuard, '/report') as UrlTree;
    expect(router.serializeUrl(result)).toBe('/login?returnUrl=%2Freport');
  });

  it('authGuard sends a user with a temporary password to change it first', () => {
    const { auth, router } = setup();
    auth.user.set({ ...MANAGER, must_change_password: true });
    expect(router.serializeUrl(runGuard(authGuard, '/') as UrlTree)).toBe('/change-password');
    expect(runGuard(authGuard, '/change-password')).toBe(true);
  });

  it('adminGuard lets Summer in and sends a manager back to the dashboard', () => {
    const { auth, router } = setup();
    auth.user.set(ADMIN);
    expect(runGuard(adminGuard, '/users')).toBe(true);
    auth.user.set(MANAGER);
    expect(router.serializeUrl(runGuard(adminGuard, '/users') as UrlTree)).toBe('/');
  });
});

describe('authInterceptor', () => {
  afterEach(() => localStorage.clear());

  it('adds the Bearer token to API calls, but not to login', () => {
    localStorage.setItem('sk.token', 'tok-123');
    const { http } = setup();
    const client = TestBed.inject(HttpClient);
    client.get('/api/dashboard').subscribe();
    client.post('/api/auth/login', 'username=a&password=b').subscribe();
    expect(http.expectOne('/api/dashboard').request.headers.get('Authorization')).toBe(
      'Bearer tok-123',
    );
    expect(http.expectOne('/api/auth/login').request.headers.has('Authorization')).toBe(false);
  });

  it('on 401 drops the token and goes to sign-in', async () => {
    localStorage.setItem('sk.token', 'expired');
    const { http, auth, router } = setup();
    auth.user.set(MANAGER);
    const nav = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    TestBed.inject(HttpClient)
      .get('/api/dashboard')
      .subscribe({ error: () => undefined });
    http.expectOne('/api/dashboard').flush({ detail: 'expired' }, { status: 401, statusText: 'x' });
    expect(auth.user()).toBeNull();
    expect(auth.token()).toBeNull();
    expect(localStorage.getItem('sk.token')).toBeNull();
    expect(nav).toHaveBeenCalledWith(['/login'], expect.anything());
  });
});

describe('uploadActions (what each role may do; the API enforces the same)', () => {
  const mine = { status: 'active' as const, uploaded_by_id: MANAGER.id };
  const theirs = { status: 'active' as const, uploaded_by_id: 99 };

  it("a manager can flag their own upload, not someone else's, and never void", () => {
    expect(uploadActions(mine, MANAGER)).toEqual({ flag: true, dismiss: false, void: false });
    expect(uploadActions(theirs, MANAGER)).toEqual({ flag: false, dismiss: false, void: false });
  });

  it('Summer can flag, dismiss a flag and void', () => {
    expect(uploadActions(theirs, ADMIN)).toEqual({ flag: true, dismiss: false, void: true });
    expect(uploadActions({ ...theirs, status: 'flagged_mistake' }, ADMIN)).toEqual({
      flag: true,
      dismiss: true,
      void: true,
    });
    expect(uploadActions({ ...theirs, status: 'voided' }, ADMIN).void).toBe(false);
  });
});

describe('App shell by role', () => {
  async function shell(me: Me) {
    const { auth, http } = setup();
    auth.user.set(me);
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    // Summer's pending-review badge polls the count.
    if (me.role === 'admin') {
      http.expectOne('/api/uploads/pending-review/count').flush({ count: 2 });
    }
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    (el.querySelector('[data-testid="account"]') as HTMLButtonElement).click();
    await fixture.whenStable();
    return { el, overlay: document.querySelector('.cdk-overlay-container') as HTMLElement };
  }

  afterEach(() => document.querySelector('.cdk-overlay-container')?.replaceChildren());

  it('admin sees Users, Audit and Review with the pending count', async () => {
    const { el, overlay } = await shell(ADMIN);
    expect(overlay.querySelector('[data-testid="menu-users"]')).not.toBeNull();
    expect(overlay.textContent).toContain('Audit log');
    expect(el.querySelector('[data-testid="nav-review"]')?.textContent).toContain('2');
  });

  it('a branch manager sees neither Users nor Review', async () => {
    const { el, overlay } = await shell(MANAGER);
    expect(overlay.querySelector('[data-testid="menu-users"]')).toBeNull();
    expect(overlay.textContent).not.toContain('Audit log');
    expect(overlay.textContent).toContain('Branch manager · Rishon LeZion');
    expect(el.querySelector('[data-testid="nav-review"]')).toBeNull();
  });
});
