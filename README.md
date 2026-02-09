# 🐷 Team Sir Pork a Lot — Raffle Ticket Site

A virtual raffle ticket sales website for **Team Sir Pork a Lot** at Hogs for the Cause 2026.

## Tech Stack

- **Next.js 15** (App Router)
- **TypeScript** + **Tailwind CSS**
- **Stripe Checkout** — secure payment processing
- **Supabase** — PostgreSQL database for order tracking
- **Vercel** — hosting

## Getting Started

### 1. Clone & Install

```bash
git clone https://github.com/StevieSimsII/Team_Sir_Pork_a_Lot.git
cd Team_Sir_Pork_a_Lot
npm install
```

### 2. Set Up Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Run the SQL in `supabase/schema.sql` in the Supabase SQL Editor
3. Copy your project URL, anon key, and service role key

### 3. Set Up Stripe

1. Go to [dashboard.stripe.com](https://dashboard.stripe.com)
2. Copy your **Secret Key** from Developers → API Keys
3. Set up a webhook endpoint pointing to `https://your-domain.com/api/webhook`
   - Listen for: `checkout.session.completed`, `checkout.session.expired`
4. Copy the **Webhook Signing Secret**

### 4. Configure Environment Variables

```bash
cp .env.local.example .env.local
```

Fill in your keys:

| Variable | Description |
|---|---|
| `STRIPE_SECRET_KEY` | Stripe secret key (starts with `sk_`) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret (starts with `whsec_`) |
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (for webhooks) |

### 5. Run Locally

```bash
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000)

## Deploy to Vercel

1. Push to GitHub
2. Import the repo at [vercel.com/new](https://vercel.com/new)
3. Add all environment variables from `.env.local` to Vercel's Environment Variables settings
4. Deploy!

After deploying, update your Stripe webhook URL to your production domain.

## Ticket Pricing

| Tickets | Price | Per Ticket |
|---------|-------|------------|
| 1 | $25 | $25.00 |
| 3 | $60 | $20.00 |
| 6 | $100 | $16.67 |
| 12 | $200 | $16.67 |

## How It Works

1. User fills out name, email, and phone number
2. Selects a ticket tier
3. Clicks "Purchase Tickets" → redirected to Stripe Checkout
4. After payment, Stripe webhook updates the order status to **paid** in Supabase
5. User sees a success confirmation page
