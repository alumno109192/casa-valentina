import { Component, computed, effect, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import {
  ApiService,
  Category,
  Order,
  Product,
  SaleIn,
  Variant,
  formatCents,
  formatEuros,
  parseCents,
  quickCashOptions,
} from 'shared';

import { DraftLine, OrderStore } from '../../state/order-store';

type Overlay = 'none' | 'variant' | 'cash' | 'card' | 'openPrice' | 'line';

/** Pantalla de cobro: familias, botonera y pedido en curso. */
@Component({
  selector: 'pos-till',
  templateUrl: './till.html',
  styleUrl: './till.scss',
})
export class Till {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly order = inject(OrderStore);

  readonly categories = signal<Category[]>([]);
  readonly selectedCategoryId = signal<string | null>(null);
  readonly search = signal('');
  readonly online = signal(true);
  readonly loadError = signal<string | null>(null);
  readonly busy = signal(false);

  readonly overlay = signal<Overlay>('none');
  readonly pendingProduct = signal<Product | null>(null);
  readonly editingLine = signal<DraftLine | null>(null);
  readonly lastTicket = signal<Order | null>(null);

  /** Lo que el cajero teclea en el cobro en efectivo. */
  readonly tenderedText = signal('');
  readonly openPriceName = signal('');
  readonly openPriceText = signal('');
  readonly paymentError = signal<string | null>(null);

  readonly staffName = computed(() => this.api.session()?.name ?? '');

  readonly selectedCategory = computed(() => {
    const id = this.selectedCategoryId();
    return this.categories().find((category) => category.id === id) ?? null;
  });

  /** Con buscador activo manda el buscador; si no, la familia elegida. */
  readonly visibleProducts = computed<Product[]>(() => {
    const term = this.search().trim().toLowerCase();
    if (term.length >= 2) {
      return this.categories()
        .flatMap((category) => category.products)
        .filter((product) => product.name.toLowerCase().includes(term))
        .slice(0, 60);
    }
    return this.selectedCategory()?.products ?? [];
  });

  readonly totalCents = computed(() => this.order.totalCents());

  readonly changeCents = computed(() => {
    const tendered = parseCents(this.tenderedText());
    if (tendered === null) {
      return null;
    }
    return tendered - this.totalCents();
  });

  readonly quickCash = computed(() => quickCashOptions(this.totalCents()));

  constructor() {
    if (!this.api.session()) {
      void this.router.navigate(['/']);
    }
    this.loadCatalog();

    // Indicador de conexión: el TPV avisa antes de que el cajero lo note
    effect((onCleanup) => {
      const timer = setInterval(() => {
        this.api.health().subscribe({
          next: () => this.online.set(true),
          error: () => this.online.set(false),
        });
      }, 15000);
      onCleanup(() => clearInterval(timer));
    });
  }

  // --- Catálogo -------------------------------------------------------------

  loadCatalog(): void {
    this.api.catalogForPos().subscribe({
      next: (categories) => {
        this.categories.set(categories);
        this.loadError.set(null);
        this.online.set(true);
        if (!this.selectedCategoryId() && categories.length) {
          this.selectedCategoryId.set(categories[0].id);
        }
      },
      error: () => {
        this.online.set(false);
        this.loadError.set(
          'No se pudo cargar el catálogo. Comprueba la red del local.',
        );
      },
    });
  }

  selectCategory(category: Category): void {
    this.selectedCategoryId.set(category.id);
    this.search.set('');
  }

  // --- Añadir al pedido -----------------------------------------------------

  tapProduct(product: Product): void {
    if (!product.is_available) {
      return;
    }
    if (product.is_open_price) {
      this.pendingProduct.set(product);
      this.openPriceName.set(product.name);
      this.openPriceText.set('');
      this.overlay.set('openPrice');
      return;
    }

    const variants = product.variants;
    if (variants.length > 1) {
      this.pendingProduct.set(product);
      this.overlay.set('variant');
      return;
    }
    if (variants.length === 1) {
      this.order.addVariant(product, variants[0]);
    }
  }

  chooseVariant(variant: Variant): void {
    const product = this.pendingProduct();
    if (product) {
      this.order.addVariant(product, variant);
    }
    this.closeOverlay();
  }

  confirmOpenPrice(): void {
    const product = this.pendingProduct();
    const cents = parseCents(this.openPriceText());
    const name = this.openPriceName().trim();

    if (!product || !name || cents === null || cents <= 0) {
      this.paymentError.set('Hace falta un concepto y un importe');
      return;
    }
    this.order.addOpenPrice(name, cents, product.category_id, product.vat_rate);
    this.closeOverlay();
  }

  // --- Teclado numérico -----------------------------------------------------

  pressDigit(digit: number): void {
    this.order.pushDigit(digit);
  }

  clearQuantity(): void {
    this.order.clearPendingQuantity();
  }

  // --- Línea ----------------------------------------------------------------

  editLine(line: DraftLine): void {
    this.editingLine.set(line);
    this.overlay.set('line');
  }

  changeQuantity(delta: number): void {
    const line = this.editingLine();
    if (!line) {
      return;
    }
    const quantity = line.quantity + delta;
    this.order.setQuantity(line.key, quantity);
    if (quantity <= 0) {
      this.closeOverlay();
      return;
    }
    this.editingLine.set({ ...line, quantity });
  }

  removeLine(): void {
    const line = this.editingLine();
    if (line) {
      this.order.remove(line.key);
    }
    this.closeOverlay();
  }

  // --- Cobro ----------------------------------------------------------------

  startCash(): void {
    if (this.order.isEmpty()) {
      return;
    }
    this.tenderedText.set('');
    this.paymentError.set(null);
    this.overlay.set('cash');
  }

  startCard(): void {
    if (this.order.isEmpty()) {
      return;
    }
    this.paymentError.set(null);
    this.overlay.set('card');
  }

  setTendered(cents: number): void {
    this.tenderedText.set(formatCents(cents));
  }

  pressTenderDigit(digit: string): void {
    this.tenderedText.update((text) => (text === '0' ? digit : text + digit));
  }

  clearTender(): void {
    this.tenderedText.set('');
  }

  confirmCash(): void {
    const tendered = parseCents(this.tenderedText());
    const total = this.totalCents();
    if (tendered === null || tendered < total) {
      this.paymentError.set('Lo entregado no cubre el total');
      return;
    }
    this.charge([
      { method: 'cash', amount_cents: total, tendered_cents: tendered },
    ]);
  }

  confirmCard(): void {
    this.charge([{ method: 'card', amount_cents: this.totalCents() }]);
  }

  private charge(payments: SaleIn['payments']): void {
    this.busy.set(true);
    const sale: SaleIn = {
      id: crypto.randomUUID(),
      lines: this.order.toLinesIn(),
      payments,
      channel: 'counter',
    };

    this.api.createSale(sale).subscribe({
      next: (ticket) => {
        this.busy.set(false);
        this.lastTicket.set(ticket);
        this.order.clear();
        this.closeOverlay();
        // Aquí irá la impresión en la Sunmi (fase 1, plugin de Capacitor)
      },
      error: (response: { status: number; error?: { detail?: string } }) => {
        this.busy.set(false);
        this.paymentError.set(
          response.status === 0
            ? 'Sin conexión: la venta no se ha grabado'
            : (response.error?.detail ?? 'No se pudo grabar la venta'),
        );
      },
    });
  }

  closeOverlay(): void {
    this.overlay.set('none');
    this.pendingProduct.set(null);
    this.editingLine.set(null);
    this.paymentError.set(null);
  }

  dismissTicket(): void {
    this.lastTicket.set(null);
  }

  logout(): void {
    this.api.logout();
    this.order.clear();
    void this.router.navigate(['/']);
  }

  // Formateo para la plantilla
  readonly euros = formatEuros;
  readonly cents = formatCents;
}
