/** Cliente HTTP de la API del local. */

import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, InjectionToken, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';
import { tap } from 'rxjs/operators';

import { Category, DailySpecial } from '../models/catalog';
import {
  CashSession,
  DayBoard,
  Deposit,
  Order,
  Preorder,
  SaleIn,
  Session,
  ZReport,
} from '../models/sales';

/** URL del backend. Cada app la aporta en su configuración de entorno. */
export const API_BASE_URL = new InjectionToken<string>('API_BASE_URL');

const TOKEN_KEY = 'tpv.session';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  /** Sesión del cajero. Se guarda para que un refresco no eche a nadie. */
  readonly session = signal<Session | null>(this.restoreSession());

  private restoreSession(): Session | null {
    try {
      const raw = localStorage.getItem(TOKEN_KEY);
      return raw ? (JSON.parse(raw) as Session) : null;
    } catch {
      return null;
    }
  }

  private get headers(): HttpHeaders {
    const token = this.session()?.token;
    return new HttpHeaders(token ? { Authorization: `Bearer ${token}` } : {});
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  // --- Sesión ---------------------------------------------------------------

  login(pin: string, deviceId?: string): Observable<Session> {
    return this.http
      .post<Session>(this.url('/api/auth/login'), { pin, device_id: deviceId })
      .pipe(
        tap((session) => {
          this.session.set(session);
          try {
            localStorage.setItem(TOKEN_KEY, JSON.stringify(session));
          } catch {
            // Modo privado o almacenamiento lleno: la sesión vive en memoria
          }
        }),
      );
  }

  logout(): void {
    this.session.set(null);
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      // nada que limpiar
    }
  }

  // --- Catálogo -------------------------------------------------------------

  catalogForPos(): Observable<Category[]> {
    return this.http.get<Category[]>(this.url('/api/catalog/pos'));
  }

  catalogForMenu(): Observable<Category[]> {
    return this.http.get<Category[]>(this.url('/api/catalog/menu'));
  }

  dailySpecial(): Observable<DailySpecial | null> {
    return this.http.get<DailySpecial | null>(this.url('/api/catalog/daily-special'));
  }

  setAvailability(productId: string, available: boolean): Observable<unknown> {
    return this.http.patch(
      this.url(`/api/catalog/products/${productId}`),
      { is_available: available },
      { headers: this.headers },
    );
  }

  // --- Ventas ---------------------------------------------------------------

  createSale(sale: SaleIn): Observable<Order> {
    return this.http.post<Order>(this.url('/api/sales'), sale, {
      headers: this.headers,
    });
  }

  salesOfDay(day?: string): Observable<Order[]> {
    const query = day ? `?day=${day}` : '';
    return this.http.get<Order[]>(this.url(`/api/sales${query}`), {
      headers: this.headers,
    });
  }

  refund(orderId: string, lineIds?: string[], reason?: string): Observable<Order> {
    return this.http.post<Order>(
      this.url(`/api/sales/${orderId}/refund`),
      { line_ids: lineIds ?? null, reason: reason ?? null },
      { headers: this.headers },
    );
  }

  // --- Caja -----------------------------------------------------------------

  currentCashSession(): Observable<CashSession | null> {
    return this.http.get<CashSession | null>(this.url('/api/cash/session'), {
      headers: this.headers,
    });
  }

  openCashSession(openingFloatCents: number): Observable<CashSession> {
    return this.http.post<CashSession>(
      this.url('/api/cash/session'),
      { opening_float_cents: openingFloatCents },
      { headers: this.headers },
    );
  }

  previewZ(): Observable<ZReport> {
    return this.http.get<ZReport>(this.url('/api/cash/session/z'), {
      headers: this.headers,
    });
  }

  closeCashSession(countedCashCents: number, note?: string): Observable<ZReport> {
    return this.http.post<ZReport>(
      this.url('/api/cash/session/close'),
      { counted_cash_cents: countedCashCents, close_note: note ?? null },
      { headers: this.headers },
    );
  }

  deposits(): Observable<Deposit[]> {
    return this.http.get<Deposit[]>(this.url('/api/cash/deposits'), {
      headers: this.headers,
    });
  }

  takeDeposit(amountCents: number, name?: string, phone?: string): Observable<Deposit> {
    return this.http.post<Deposit>(
      this.url('/api/cash/deposits'),
      { amount_cents: amountCents, customer_name: name, customer_phone: phone },
      { headers: this.headers },
    );
  }

  returnDeposit(depositId: string): Observable<Deposit> {
    return this.http.post<Deposit>(
      this.url(`/api/cash/deposits/${depositId}/return`),
      {},
      { headers: this.headers },
    );
  }

  // --- Encargos -------------------------------------------------------------

  dayBoard(day?: string): Observable<DayBoard> {
    const query = day ? `?day=${day}` : '';
    return this.http.get<DayBoard>(this.url(`/api/preorders/board${query}`), {
      headers: this.headers,
    });
  }

  createPreorder(payload: unknown): Observable<Preorder> {
    return this.http.post<Preorder>(this.url('/api/preorders'), payload, {
      headers: this.headers,
    });
  }

  setPreorderStatus(preorderId: string, status: string): Observable<Preorder> {
    return this.http.patch<Preorder>(
      this.url(`/api/preorders/${preorderId}/status`),
      { status },
      { headers: this.headers },
    );
  }

  health(): Observable<{ status: string }> {
    return this.http.get<{ status: string }>(this.url('/api/health'));
  }
}
