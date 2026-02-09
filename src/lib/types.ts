export interface TicketTier {
  count: number;
  price: number;
  label: string;
  savings?: string;
}

export const TICKET_TIERS: TicketTier[] = [
  { count: 1, price: 2500, label: "1 Ticket", savings: undefined },
  { count: 3, price: 6000, label: "3 Tickets", savings: "Save $15" },
  { count: 6, price: 10000, label: "6 Tickets", savings: "Save $50" },
  { count: 12, price: 20000, label: "12 Tickets", savings: "Save $100" },
];

export interface OrderFormData {
  name: string;
  email: string;
  phone: string;
  ticketCount: number;
  amount: number; // in cents
}

export interface Order {
  id: string;
  name: string;
  email: string;
  phone: string;
  ticket_count: number;
  amount: number;
  payment_status: "pending" | "paid" | "failed";
  stripe_session_id: string | null;
  created_at: string;
}
