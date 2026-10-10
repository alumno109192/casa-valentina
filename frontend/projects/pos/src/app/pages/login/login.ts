import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from 'shared';

/** Entrada al turno: cuatro dígitos, sin teclado físico. */
@Component({
  selector: 'pos-login',
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly pin = signal('');
  readonly error = signal<string | null>(null);
  readonly busy = signal(false);

  readonly keys = [1, 2, 3, 4, 5, 6, 7, 8, 9];

  press(digit: number): void {
    if (this.pin().length >= 4 || this.busy()) {
      return;
    }
    this.error.set(null);
    const next = this.pin() + String(digit);
    this.pin.set(next);
    if (next.length === 4) {
      this.submit(next);
    }
  }

  backspace(): void {
    this.pin.update((value) => value.slice(0, -1));
    this.error.set(null);
  }

  private submit(pin: string): void {
    this.busy.set(true);
    this.api.login(pin).subscribe({
      next: () => {
        this.busy.set(false);
        this.pin.set('');
        void this.router.navigate(['/tpv']);
      },
      error: (response: { status: number; error?: { detail?: string } }) => {
        this.busy.set(false);
        this.pin.set('');
        this.error.set(
          response.status === 0
            ? 'Sin conexión con el servidor del local'
            : (response.error?.detail ?? 'PIN incorrecto'),
        );
      },
    });
  }
}
