import { NextRequest, NextResponse } from "next/server";
import { stripe } from "@/lib/stripe";
import { supabase } from "@/lib/supabase";
import { TICKET_TIERS } from "@/lib/types";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { name, email, phone, ticketCount, amount } = body;

    // Validate input
    if (!name || !email || !phone || !ticketCount || !amount) {
      return NextResponse.json(
        { error: "All fields are required" },
        { status: 400 }
      );
    }

    // Validate tier exists
    const tier = TICKET_TIERS.find(
      (t) => t.count === ticketCount && t.price === amount
    );
    if (!tier) {
      return NextResponse.json(
        { error: "Invalid ticket selection" },
        { status: 400 }
      );
    }

    // Create order in Supabase with "pending" status
    const { data: order, error: dbError } = await supabase
      .from("orders")
      .insert({
        name,
        email,
        phone,
        ticket_count: ticketCount,
        amount,
        payment_status: "pending",
      })
      .select()
      .single();

    if (dbError) {
      console.error("Supabase error:", dbError);
      return NextResponse.json(
        { error: "Failed to create order" },
        { status: 500 }
      );
    }

    // Create Stripe Checkout session
    const session = await stripe.checkout.sessions.create({
      payment_method_types: ["card"],
      customer_email: email,
      line_items: [
        {
          price_data: {
            currency: "usd",
            product_data: {
              name: `Raffle Ticket${ticketCount > 1 ? "s" : ""} — Team Sir Pork a Lot`,
              description: `${ticketCount} raffle ticket${ticketCount > 1 ? "s" : ""} for Hogs for the Cause 2026`,
            },
            unit_amount: amount,
          },
          quantity: 1,
        },
      ],
      mode: "payment",
      success_url: `${req.nextUrl.origin}/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${req.nextUrl.origin}/?cancelled=true`,
      metadata: {
        order_id: order.id,
        name,
        phone,
        ticket_count: ticketCount.toString(),
      },
    });

    // Update order with stripe session ID
    await supabase
      .from("orders")
      .update({ stripe_session_id: session.id })
      .eq("id", order.id);

    return NextResponse.json({ url: session.url });
  } catch (err) {
    console.error("Checkout error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
