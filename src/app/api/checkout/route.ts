import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { TICKET_TIERS } from "@/lib/types";

// Use service role key for server-side operations (bypasses RLS)
const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

const VENMO_USERNAME = "Sir-Pork-A-Lot";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { name, email, phone, ticketCount, amount } = body;

    // Validate input
    if (!name || !phone || !ticketCount || !amount) {
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

    // Create pending order in Supabase
    const { error: dbError } = await supabase.from("orders").insert({
      name,
      email: email || null,
      phone,
      ticket_count: ticketCount,
      amount,
      payment_status: "pending",
    });

    if (dbError) {
      console.error("Supabase error:", dbError);
      return NextResponse.json(
        { error: "Failed to create order" },
        { status: 500 }
      );
    }

    // Redirect to success page — Venmo URL is built there to avoid double-encoding
    const successUrl = `/success?amount=${amount}&tickets=${ticketCount}&name=${encodeURIComponent(name)}`;

    return NextResponse.json({ url: successUrl });
  } catch (err) {
    console.error("Checkout error:", err);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
