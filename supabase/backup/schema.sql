-- SirPorkALot (hrdbdlkgeqfqyhcyrjxt) schema, 2026-10-20
-- gen_random_uuid() needs PG13+ or pgcrypto.
CREATE TABLE public.orders (
  id uuid DEFAULT gen_random_uuid() NOT NULL,
  name text NOT NULL,
  email text,
  phone text NOT NULL,
  ticket_count integer NOT NULL,
  amount integer NOT NULL,
  payment_status text DEFAULT 'pending'::text NOT NULL,
  stripe_session_id text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT orders_payment_status_check CHECK ((payment_status = ANY (ARRAY['pending'::text, 'paid'::text, 'failed'::text]))),
  CONSTRAINT orders_pkey PRIMARY KEY (id)
);

CREATE INDEX idx_orders_stripe_session ON public.orders USING btree (stripe_session_id);
CREATE INDEX idx_orders_email ON public.orders USING btree (email);

ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow limited anon inserts" ON public.orders AS PERMISSIVE FOR INSERT TO anon WITH CHECK (((payment_status = 'pending'::text) AND (stripe_session_id IS NULL) AND (ticket_count > 0) AND (amount > 0) AND (name IS NOT NULL) AND (email IS NOT NULL)));
CREATE POLICY "Allow service role full access" ON public.orders AS PERMISSIVE FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Allow authenticated reads" ON public.orders AS PERMISSIVE FOR SELECT TO authenticated USING (true);

-- public schema has no sequences, functions, or triggers (checked 2026-10-20).
-- Policies reference Supabase roles anon/authenticated/service_role; on plain Postgres/Neon create those roles first or drop the policies.
