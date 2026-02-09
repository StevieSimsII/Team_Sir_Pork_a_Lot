-- Run this in your Supabase SQL Editor to create the orders table

CREATE TABLE orders (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT NOT NULL,
  ticket_count INTEGER NOT NULL,
  amount INTEGER NOT NULL, -- stored in cents
  payment_status TEXT NOT NULL DEFAULT 'pending' CHECK (payment_status IN ('pending', 'paid', 'failed')),
  stripe_session_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Policy: Allow inserts from the anon key (public form submissions)
CREATE POLICY "Allow public inserts" ON orders
  FOR INSERT
  TO anon
  WITH CHECK (true);

-- Policy: Allow reads for authenticated users only (admin viewing)
CREATE POLICY "Allow authenticated reads" ON orders
  FOR SELECT
  TO authenticated
  USING (true);

-- Policy: Allow service role to do everything (for webhooks)
CREATE POLICY "Allow service role full access" ON orders
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Index for looking up orders by stripe session
CREATE INDEX idx_orders_stripe_session ON orders (stripe_session_id);

-- Index for looking up orders by email
CREATE INDEX idx_orders_email ON orders (email);
