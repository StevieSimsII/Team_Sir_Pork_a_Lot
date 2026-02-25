import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

const supabaseAdmin = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
);

/**
 * POST /api/mark-paid
 *
 * Called by Power Automate when a Venmo payment email is received.
 * Finds the most recent pending order matching the buyer name + amount
 * and marks it as paid.
 *
 * Headers:
 *   Authorization: Bearer <MARK_PAID_SECRET>
 *
 * Body (JSON):
 *   { "name": "John Doe", "amount": "25.00" }
 */
export async function POST(req: NextRequest) {
  // ── Auth check ──────────────────────────────────────────────────────────────
  const secret = process.env.MARK_PAID_SECRET;
  if (!secret) {
    console.error("MARK_PAID_SECRET is not configured.");
    return NextResponse.json({ error: "Server misconfiguration" }, { status: 500 });
  }

  const authHeader = req.headers.get("authorization") ?? "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : "";

  if (token !== secret) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // ── Parse body ───────────────────────────────────────────────────────────────
  let name: string | undefined;
  let amountRaw: string | undefined;

  try {
    const body = await req.json();
    name = typeof body.name === "string" ? body.name.trim() : undefined;
    amountRaw = typeof body.amount === "string" ? body.amount.trim() : undefined;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  if (!name || !amountRaw) {
    return NextResponse.json(
      { error: "Both 'name' and 'amount' are required" },
      { status: 400 }
    );
  }

  // Convert dollars ("25.00") → cents (2500)
  const amountCents = Math.round(parseFloat(amountRaw) * 100);
  if (isNaN(amountCents) || amountCents <= 0) {
    return NextResponse.json({ error: "Invalid amount" }, { status: 400 });
  }

  // ── Find the most recent pending order matching name + amount ─────────────
  const { data: orders, error: fetchError } = await supabaseAdmin
    .from("orders")
    .select("id, name, amount, payment_status, created_at")
    .ilike("name", name)          // case-insensitive match
    .eq("amount", amountCents)
    .eq("payment_status", "pending")
    .order("created_at", { ascending: false })
    .limit(1);

  if (fetchError) {
    console.error("Supabase fetch error:", fetchError);
    return NextResponse.json({ error: "Database error" }, { status: 500 });
  }

  if (!orders || orders.length === 0) {
    console.warn(`No pending order found for name="${name}" amount=${amountCents}¢`);
    return NextResponse.json(
      { error: "No matching pending order found" },
      { status: 404 }
    );
  }

  const order = orders[0];

  // ── Mark as paid ─────────────────────────────────────────────────────────────
  const { error: updateError } = await supabaseAdmin
    .from("orders")
    .update({ payment_status: "paid" })
    .eq("id", order.id);

  if (updateError) {
    console.error("Supabase update error:", updateError);
    return NextResponse.json({ error: "Failed to update order" }, { status: 500 });
  }

  console.log(`✅ Order ${order.id} marked as paid (${name}, $${amountRaw})`);
  return NextResponse.json({ success: true, orderId: order.id });
}
