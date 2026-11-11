import { BreakpointObserver, BreakpointState } from '@angular/cdk/layout';
import { TestBed } from '@angular/core/testing';
import { BehaviorSubject } from 'rxjs';
import { MOBILE_CLASS, MOBILE_QUERY, Viewport } from './viewport';

describe('Viewport', () => {
  let state: BehaviorSubject<BreakpointState>;
  const observe = vi.fn();

  beforeEach(() => {
    state = new BehaviorSubject<BreakpointState>({ matches: false, breakpoints: {} });
    observe.mockReturnValue(state);
    TestBed.configureTestingModule({
      providers: [{ provide: BreakpointObserver, useValue: { observe } }],
    });
  });

  afterEach(() => document.body.classList.remove(MOBILE_CLASS));

  it('watches the phone breakpoint', () => {
    TestBed.inject(Viewport);
    expect(observe).toHaveBeenCalledWith(MOBILE_QUERY);
  });

  it('adds mobileBreakpoint to <body> on a phone and removes it on a wider screen', () => {
    const vp = TestBed.inject(Viewport);
    TestBed.tick();
    expect(document.body.classList).not.toContain(MOBILE_CLASS);

    state.next({ matches: true, breakpoints: { [MOBILE_QUERY]: true } });
    TestBed.tick();
    expect(vp.isMobile()).toBe(true);
    expect(document.body.classList).toContain(MOBILE_CLASS);

    state.next({ matches: false, breakpoints: { [MOBILE_QUERY]: false } });
    TestBed.tick();
    expect(document.body.classList).not.toContain(MOBILE_CLASS);
  });
});
