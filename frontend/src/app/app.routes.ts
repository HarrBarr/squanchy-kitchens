import { Routes } from '@angular/router';
import { adminGuard, authGuard, guestGuard } from './core/guards';

// The guards shape the UI only; every rule is enforced again by the API.
export const routes: Routes = [
  {
    path: 'login',
    title: 'Sign in · Squanchy Kitchens',
    canActivate: [guestGuard],
    loadComponent: () => import('./login/login').then((m) => m.LoginPage),
  },
  {
    path: 'change-password',
    title: 'Change password · Squanchy Kitchens',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./change-password/change-password').then((m) => m.ChangePasswordPage),
  },
  {
    path: '',
    canActivate: [authGuard],
    children: [
      {
        path: '',
        title: 'Squanchy Kitchens',
        loadComponent: () => import('./dashboard/dashboard').then((m) => m.DashboardPage),
      },
      {
        path: 'fridges/:id',
        title: 'Fridge · Squanchy Kitchens',
        loadComponent: () =>
          import('./fridge-detail/fridge-detail').then((m) => m.FridgeDetailPage),
      },
      {
        path: 'report',
        title: 'Inspector report · Squanchy Kitchens',
        loadComponent: () => import('./report/report').then((m) => m.ReportPage),
      },
      {
        path: 'uploads',
        title: 'Uploads · Squanchy Kitchens',
        loadComponent: () => import('./uploads/uploads').then((m) => m.UploadsPage),
      },
      {
        path: 'registry',
        title: 'Logger registry · Squanchy Kitchens',
        loadComponent: () => import('./registry/registry').then((m) => m.RegistryPage),
      },
      {
        path: 'review',
        title: 'Pending review · Squanchy Kitchens',
        canActivate: [adminGuard],
        data: { review: true },
        loadComponent: () => import('./uploads/uploads').then((m) => m.UploadsPage),
      },
      {
        path: 'users',
        title: 'Users · Squanchy Kitchens',
        canActivate: [adminGuard],
        loadComponent: () => import('./users/users').then((m) => m.UsersPage),
      },
      {
        path: 'audit',
        title: 'Audit log · Squanchy Kitchens',
        canActivate: [adminGuard],
        loadComponent: () => import('./audit/audit').then((m) => m.AuditPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
