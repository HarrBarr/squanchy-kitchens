import { BreakpointObserver } from '@angular/cdk/layout';
import { DOCUMENT } from '@angular/common';
import { Injectable, Renderer2, RendererFactory2, effect, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

/** Phones: below the CDK "Small" breakpoint (600px). */
export const MOBILE_QUERY = '(max-width: 599.98px)';
export const MOBILE_CLASS = 'mobileBreakpoint';

/**
 * Tracks whether the app is on a phone-sized screen and puts the `mobileBreakpoint` class on
 * <body>. It goes on <body>, not the app root, so overlays rendered outside the app (the
 * upload dialog, select and autocomplete panels) get the mobile sizing too. Component styles
 * use `:host-context(.mobileBreakpoint)`, global styles `.mobileBreakpoint …`.
 */
@Injectable({ providedIn: 'root' })
export class Viewport {
  private readonly renderer: Renderer2 = inject(RendererFactory2).createRenderer(null, null);
  private readonly body = inject(DOCUMENT).body;

  readonly isMobile = toSignal(
    inject(BreakpointObserver)
      .observe(MOBILE_QUERY)
      .pipe(map((state) => state.matches)),
    { initialValue: false },
  );

  constructor() {
    effect(() => {
      if (this.isMobile()) this.renderer.addClass(this.body, MOBILE_CLASS);
      else this.renderer.removeClass(this.body, MOBILE_CLASS);
    });
  }
}
