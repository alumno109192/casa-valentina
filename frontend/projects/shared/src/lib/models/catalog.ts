/** Tipos del catálogo. Todos los importes son céntimos enteros. */

export interface Variant {
  id: string;
  name: string;
  price_cents: number;
  sort_order: number;
  is_default: boolean;
}

export interface Product {
  id: string;
  category_id: string;
  name: string;
  short_name: string;
  description: string | null;
  image_url: string | null;
  vat_rate: number;
  is_open_price: boolean;
  is_available: boolean;
  show_in_pos: boolean;
  show_in_menu: boolean;
  sort_order: number;
  variants: Variant[];
}

export interface Category {
  id: string;
  name: string;
  color: string;
  sort_order: number;
  show_in_pos: boolean;
  show_in_menu: boolean;
  products: Product[];
}

export interface DailySpecial {
  id: string;
  day: string;
  title: string;
  description: string | null;
  price_cents: number | null;
}
