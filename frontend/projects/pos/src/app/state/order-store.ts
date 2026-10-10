/**
 * Pedido en curso.
 *
 * Los importes de línea se calculan en el cliente solo para pintarlos; el
 * total que vale es el que devuelve el servidor al cobrar, que es quien
 * reparte el IVA por tipos.
 */

import { Injectable, computed, signal } from '@angular/core';
import { LineIn, Product, Variant } from 'shared';

export interface DraftLine {
  /** Identificador local, para poder editar la línea antes de cobrar. */
  key: string;
  variantId: string | null;
  name: string;
  unitPriceCents: number;
  quantity: number;
  vatRate: number;
  note: string | null;
  /** Línea de precio libre: necesita familia para contar en los informes. */
  openPriceName?: string;
  openPriceCategoryId?: string;
}

let counter = 0;
const nextKey = () => `l${++counter}`;

/**
 * `crypto.randomUUID` solo existe en contexto seguro: servido por http a una
 * tablet de la red local sería `undefined` y el botón de cobrar estallaría sin
 * mensaje. El respaldo es suficiente para desduplicar un reenvío.
 */
function newId(): string {
  const api = globalThis.crypto;
  if (api && typeof api.randomUUID === 'function') {
    return api.randomUUID();
  }
  return `tpv-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

@Injectable({ providedIn: 'root' })
export class OrderStore {
  readonly lines = signal<DraftLine[]>([]);

  /**
   * Identificador de esta venta, estable mientras el pedido siga en curso.
   *
   * Es la mitad cliente de la idempotencia que ya ofrece el servidor: si la
   * petición llega al mini-PC y la respuesta se pierde, el cajero vuelve a
   * pulsar Cobrar y el backend reconoce el mismo id en lugar de grabar un
   * segundo ticket. Generarlo dentro de cada intento de cobro, como se hacía
   * antes, anulaba la garantía por completo y cobraba dos veces.
   */
  readonly draftId = signal<string>(newId());

  /** Cantidad teclada antes de pulsar el producto: 3 + Pollo = 3 pollos. */
  readonly pendingQuantity = signal<number | null>(null);

  readonly totalCents = computed(() =>
    this.lines().reduce((sum, line) => sum + line.unitPriceCents * line.quantity, 0),
  );

  readonly itemCount = computed(() =>
    this.lines().reduce((sum, line) => sum + line.quantity, 0),
  );

  readonly isEmpty = computed(() => this.lines().length === 0);

  addVariant(product: Product, variant: Variant, quantity?: number): void {
    const units = quantity ?? this.takePendingQuantity();
    const name =
      variant.is_default ? product.name : `${product.name} (${variant.name})`;

    // Si ya está la misma variante sin nota, se acumula en lugar de repetir fila
    const existing = this.lines().find(
      (line) => line.variantId === variant.id && !line.note,
    );
    if (existing) {
      this.setQuantity(existing.key, existing.quantity + units);
      return;
    }

    this.lines.update((lines) => [
      ...lines,
      {
        key: nextKey(),
        variantId: variant.id,
        name,
        unitPriceCents: variant.price_cents,
        quantity: units,
        vatRate: product.vat_rate,
        note: null,
      },
    ]);
  }

  /** Producto de precio libre: el cajero teclea nombre e importe. */
  addOpenPrice(
    name: string,
    priceCents: number,
    categoryId: string,
    vatRate: number,
    quantity?: number,
  ): void {
    this.lines.update((lines) => [
      ...lines,
      {
        key: nextKey(),
        variantId: null,
        name,
        unitPriceCents: priceCents,
        quantity: quantity ?? this.takePendingQuantity(),
        vatRate,
        note: null,
        openPriceName: name,
        openPriceCategoryId: categoryId,
      },
    ]);
  }

  setQuantity(key: string, quantity: number): void {
    if (quantity <= 0) {
      this.remove(key);
      return;
    }
    this.lines.update((lines) =>
      lines.map((line) => (line.key === key ? { ...line, quantity } : line)),
    );
  }

  setNote(key: string, note: string | null): void {
    this.lines.update((lines) =>
      lines.map((line) => (line.key === key ? { ...line, note } : line)),
    );
  }

  remove(key: string): void {
    this.lines.update((lines) => lines.filter((line) => line.key !== key));
  }

  clear(): void {
    this.lines.set([]);
    this.pendingQuantity.set(null);
    // Pedido nuevo, venta nueva: el id solo se renueva aquí, nunca al
    // reintentar un cobro que pudo haberse grabado.
    this.draftId.set(newId());
  }

  /** Digitos del teclado numérico acumulados como cantidad. */
  pushDigit(digit: number): void {
    const current = this.pendingQuantity() ?? 0;
    const next = current * 10 + digit;
    this.pendingQuantity.set(next > 999 ? 999 : next);
  }

  clearPendingQuantity(): void {
    this.pendingQuantity.set(null);
  }

  private takePendingQuantity(): number {
    const pending = this.pendingQuantity();
    this.pendingQuantity.set(null);
    return pending && pending > 0 ? pending : 1;
  }

  /** Convierte el pedido en el cuerpo que espera la API. */
  toLinesIn(): LineIn[] {
    return this.lines().map((line) =>
      line.variantId
        ? {
            variant_id: line.variantId,
            quantity: line.quantity,
            note: line.note,
          }
        : {
            quantity: line.quantity,
            note: line.note,
            open_price_name: line.openPriceName,
            open_price_cents: line.unitPriceCents,
            open_price_category_id: line.openPriceCategoryId,
            open_price_vat_rate: line.vatRate,
          },
    );
  }
}
