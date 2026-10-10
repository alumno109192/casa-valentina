/**
 * Salida de un 401.
 *
 * El token dura una jornada larga a propósito (el TPV no debe caducar en
 * servicio), pero si caduca o el backend se reinicia, todas las llamadas
 * responden 401. Sin esto, el cajero se queda en la pantalla de cobro viendo
 * «No se pudo grabar la venta» una y otra vez, sin volver nunca a la entrada
 * de PIN.
 *
 * El pedido en curso NO se borra: `OrderStore` vive en la raíz y sobrevive a
 * la navegación, así que al volver a entrar las líneas siguen ahí.
 */

import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { ApiService } from './api';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const api = inject(ApiService);
  const router = inject(Router);

  return next(request).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401) {
        api.logout();
        void router.navigate(['/']);
      }
      return throwError(() => error);
    }),
  );
};
