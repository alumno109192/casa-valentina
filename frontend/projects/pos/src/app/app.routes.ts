import { Routes } from '@angular/router';

import { Login } from './pages/login/login';
import { Till } from './pages/till/till';

export const routes: Routes = [
  { path: '', component: Login },
  { path: 'tpv', component: Till },
  { path: '**', redirectTo: '' },
];
