/**
 * Dinero en céntimos enteros, nunca float.
 *
 * El cálculo del IVA lo hace el servidor (app/core/money.py); aquí solo se
 * formatea y se parsea lo que teclea el cajero.
 */

/** 1250 -> '12,50'. Sin símbolo de moneda. */
export function formatCents(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const abs = Math.abs(cents);
  const units = Math.floor(abs / 100);
  const hundredths = abs % 100;
  return `${sign}${units},${String(hundredths).padStart(2, '0')}`;
}

/** 1250 -> '12,50 €'. Para pantalla, no para cálculo. */
export function formatEuros(cents: number): string {
  return `${formatCents(cents)} €`;
}

/** '12,50' o '12.50' -> 1250. Devuelve null si no es un importe válido. */
export function parseCents(text: string): number | null {
  const normalized = text.trim().replace(/\s/g, '').replace(',', '.');
  if (!normalized || !/^-?\d*\.?\d*$/.test(normalized)) {
    return null;
  }
  const value = Number(normalized);
  if (Number.isNaN(value)) {
    return null;
  }
  return Math.round(value * 100);
}

/**
 * Importes de los botones rápidos de efectivo: el exacto y los billetes
 * usuales que lo superan.
 */
export function quickCashOptions(totalCents: number): number[] {
  const notes = [500, 1000, 2000, 5000];
  const options = notes.filter((note) => note > totalCents);
  return [totalCents, ...options];
}
