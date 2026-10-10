/** Tipos de venta, caja y encargos. Espejo de app/schemas/sales.py. */

export type PaymentMethod = 'cash' | 'card';
export type Channel = 'counter' | 'phone' | 'whatsapp' | 'menu_online';

export interface LineIn {
  variant_id?: string;
  quantity: number;
  note?: string | null;
  open_price_name?: string;
  open_price_cents?: number;
  open_price_category_id?: string;
  open_price_vat_rate?: number;
}

export interface PaymentIn {
  method: PaymentMethod;
  amount_cents: number;
  tendered_cents?: number | null;
}

export interface SaleIn {
  /** Lo genera el TPV: reenviar la venta tras un corte de red no la duplica. */
  id: string;
  lines: LineIn[];
  payments: PaymentIn[];
  channel: Channel;
  preorder_id?: string | null;
  session_id?: string | null;
  customer_nif?: string | null;
  customer_name?: string | null;
  note?: string | null;
}

export interface VatGroup {
  rate: number;
  gross_cents: number;
  base_cents: number;
  vat_cents: number;
}

export interface OrderLine {
  id: string;
  name_snapshot: string;
  unit_price_cents: number;
  quantity: number;
  vat_rate: number;
  line_total_cents: number;
  note: string | null;
}

export interface Payment {
  id: string;
  method: PaymentMethod;
  amount_cents: number;
  tendered_cents: number | null;
  change_cents: number | null;
}

export interface Order {
  id: string;
  status: string;
  channel: Channel;
  ticket_full_number: string | null;
  total_cents: number;
  base_cents: number;
  vat_cents: number;
  vat_breakdown: VatGroup[] | null;
  customer_nif: string | null;
  customer_name: string | null;
  refunds_order_id: string | null;
  note: string | null;
  closed_at: string | null;
  lines: OrderLine[];
  payments: Payment[];
}

export interface CashSession {
  id: string;
  z_number: number | null;
  opened_at: string | null;
  opening_float_cents: number;
  closed_at: string | null;
  counted_cash_cents: number | null;
  expected_cash_cents: number | null;
  card_total_cents: number | null;
  difference_cents: number | null;
  close_note: string | null;
}

export interface ZReport {
  session: CashSession;
  ticket_count: number;
  sales_total_cents: number;
  cash_sales_cents: number;
  card_sales_cents: number;
  movements_cents: number;
  expected_cash_cents: number;
  counted_cash_cents: number | null;
  difference_cents: number | null;
  vat_breakdown: VatGroup[];
  /** Falso mientras el datáfono no esté integrado. */
  card_reconciled: boolean;
}

export interface Deposit {
  id: string;
  item: string;
  customer_name: string | null;
  customer_phone: string | null;
  amount_cents: number;
  status: string;
}

export interface PreorderLine {
  id: string;
  variant_id: string | null;
  name_snapshot: string;
  quantity: number;
  note: string | null;
}

export interface Preorder {
  id: string;
  customer_name: string;
  customer_phone: string | null;
  pickup_date: string;
  pickup_time: string;
  status: 'pending' | 'ready' | 'collected' | 'cancelled' | 'no_show';
  channel: Channel;
  notes: string | null;
  lines: PreorderLine[];
}

export interface SlotLoad {
  slot: string;
  product: string;
  quantity: number;
}

export interface DayBoard {
  day: string;
  preorders: Preorder[];
  load: SlotLoad[];
}

export interface Session {
  token: string;
  staff_id: string;
  name: string;
  role: 'owner' | 'cashier';
}
