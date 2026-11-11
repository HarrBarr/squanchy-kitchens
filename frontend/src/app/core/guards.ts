import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { Auth } from './auth';

/** Signed in, and no pending forced password change (unless going to change it). */
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(Auth);
  const router = inject(Router);
  const user = auth.user();
  if (!user) return router.createUrlTree(['/login'], { queryParams: { returnUrl: state.url } });
  if (user.must_change_password && !state.url.startsWith('/change-password')) {
    return router.createUrlTree(['/change-password']);
  }
  return true;
};

/** Admin-only screens. A manager is sent back to their dashboard. */
export const adminGuard: CanActivateFn = () => {
  const auth = inject(Auth);
  return auth.isAdmin() ? true : inject(Router).createUrlTree(['/']);
};

/** The sign-in page is for signed-out users only. */
export const guestGuard: CanActivateFn = () => {
  const auth = inject(Auth);
  return auth.user() ? inject(Router).createUrlTree(['/']) : true;
};
