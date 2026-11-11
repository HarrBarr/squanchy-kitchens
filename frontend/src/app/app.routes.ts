import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    title: 'Squanchy Kitchens',
    loadComponent: () => import('./dashboard/dashboard').then((m) => m.DashboardPage),
  },
  {
    path: 'fridges/:id',
    title: 'Fridge · Squanchy Kitchens',
    loadComponent: () => import('./fridge-detail/fridge-detail').then((m) => m.FridgeDetailPage),
  },
  {
    path: 'report',
    title: 'Inspector report · Squanchy Kitchens',
    loadComponent: () => import('./report/report').then((m) => m.ReportPage),
  },
  {
    path: 'registry',
    title: 'Logger registry · Squanchy Kitchens',
    loadComponent: () => import('./registry/registry').then((m) => m.RegistryPage),
  },
  { path: '**', redirectTo: '' },
];
