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

/**
 * '12,50' o '12.50' -> 1250. Devuelve null si no es un importe válido.
 *
 * Se parsea por partes y no con `Number`: `Math.round(Number('20.005') * 100)`
 * daba 2001 en lugar de 2000 (el float es 20.004999...), así que un dígito de
 * más tras pulsar «Exacto» metía un céntimo de descuadre en el cambio. Y la
 * coma repetida ('1,2,5') pasaba el filtro y luego devolvía null, con lo que
 * el cajero veía «lo entregado no cubre el total» habiendo teclado de más.
 *
 * No admite negativos: en el mostrador no se teclea un importe negativo, y
 * las devoluciones van por su propio circuito, que exige permiso de dueño.
 */
export function parseCents(text: string): number | null {
  const normalized = text.trim().replace(/\s/g, '').replace(/,/g, '.');
  if (!/^\d+(\.\d{0,2})?$/.test(normalized)) {
    return null;
  }
  const [units, hundredths = ''] = normalized.split('.');
  return Number(units) * 100 + Number(hundredths.padEnd(2, '0'));
}

/**
 * Importes de los botones rápidos de efectivo: el exacto, el redondeo al euro
 * y a los cinco euros siguientes, y los billetes que superan el total.
 *
 * Antes solo ofrecía billetes estrictamente mayores que el total, así que con
 * una cuenta de 52,00 € el único botón era «Exacto» y había que teclear a
 * mano. El redondeo al euro es además el gesto más habitual del mostrador.
 */
export function quickCashOptions(totalCents: number): number[] {
  const nextEuro = Math.ceil(totalCents / 100) * 100;
  const nextFive = Math.ceil(totalCents / 500) * 500;
  const notes = [500, 1000, 2000, 5000, 10000];
  const candidates = [nextEuro, nextFive, ...notes].filter(
    (amount) => amount > totalCents,
  );
  const unique = [...new Set(candidates)].sort((a, b) => a - b);
  return [totalCents, ...unique.slice(0, 4)];
}
