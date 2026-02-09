import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";
import { createClient } from "@supabase/supabase-js";

// Use service role key for webhook (bypasses RLS)
const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

export async function POST(req: NextRequest) {
  const body = await req.text();
  const sig = req.headers.get("stripe-signature");

  if (!sig) {
    return NextResponse.json(
      { error: "Missing stripe-signature header" },
      { status: 400 }
    );
  }

  let event;

  try {
    event = stripe.webhooks.constructEvent(
      body,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET!
    );
  } catch (err) {
    console.error("Webhook signature verification failed:", err);
    return NextResponse.json(
      { error: "Webhook signature verification failed" },
      { status: 400 }
    );
  }

  // Handle the checkout.session.completed event
  if (event.type === "checkout.session.completed") {
    const session = event.data.object;

    const orderId = session.metadata?.order_id;

    if (orderId) {
      const { error } = await supabaseAdmin
        .from("orders")
        .update({ payment_status: "paid" })
        .eq("id", orderId);

      if (error) {
        console.error("Failed to update order:", error);
        return NextResponse.json(
          { error: "Failed to update order" },
          { status: 500 }
        );
      }

      console.log(`✅ Order ${orderId} marked as paid`);
    }
  }

  // Handle failed payments
  if (event.type === "checkout.session.expired") {
    const session = event.data.object;
    const orderId = session.metadata?.order_id;

    if (orderId) {
      await supabaseAdmin
        .from("orders")
        .update({ payment_status: "failed" })
        .eq("id", orderId);

      console.log(`❌ Order ${orderId} marked as failed`);
    }
  }

  return NextResponse.json({ received: true });
}
