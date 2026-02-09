"use client";

import { useState } from "react";
import TicketSelector from "./TicketSelector";
import { TicketTier } from "@/lib/types";

export default function PurchaseForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [selectedTier, setSelectedTier] = useState<TicketTier | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isValid =
    name.trim() && email.trim() && phone.trim() && selectedTier !== null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid || !selectedTier) return;

    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim(),
          phone: phone.trim(),
          ticketCount: selectedTier.count,
          amount: selectedTier.price,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Something went wrong");
      }

      // Redirect to Stripe Checkout
      window.location.href = data.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      {/* Contact Info */}
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-[#DAA520] flex items-center gap-2">
          <span className="text-2xl">📋</span> Your Information
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="name" className="block text-sm mb-1 text-[#FFF8DC]/70">
              Full Name *
            </label>
            <input
              id="name"
              type="text"
              className="form-input"
              placeholder="John Doe"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div>
            <label htmlFor="phone" className="block text-sm mb-1 text-[#FFF8DC]/70">
              Phone Number *
            </label>
            <input
              id="phone"
              type="tel"
              className="form-input"
              placeholder="(555) 123-4567"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
          </div>
        </div>
        <div>
          <label htmlFor="email" className="block text-sm mb-1 text-[#FFF8DC]/70">
            Email Address *
          </label>
          <input
            id="email"
            type="email"
            className="form-input"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
      </div>

      {/* Ticket Selection */}
      <div className="space-y-4">
        <h3 className="text-xl font-bold text-[#DAA520] flex items-center gap-2">
          <span className="text-2xl">🎟️</span> Select Your Tickets
        </h3>
        <TicketSelector selected={selectedTier} onSelect={setSelectedTier} />
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/40 border border-red-500/50 text-red-200 rounded-lg p-4 text-sm">
          {error}
        </div>
      )}

      {/* Submit */}
      <div className="text-center">
        {selectedTier && (
          <p className="text-lg mb-4 text-[#FFF8DC]/80">
            Total:{" "}
            <span className="text-2xl font-bold text-[#DAA520]">
              ${(selectedTier.price / 100).toFixed(0)}
            </span>{" "}
            for {selectedTier.count} ticket{selectedTier.count > 1 ? "s" : ""}
          </p>
        )}
        <button
          type="submit"
          disabled={!isValid || loading}
          className="btn-fire text-lg px-10 py-4 w-full sm:w-auto"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg
                className="animate-spin h-5 w-5"
                viewBox="0 0 24 24"
                fill="none"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Processing...
            </span>
          ) : (
            "🔥 Purchase Tickets 🔥"
          )}
        </button>
      </div>
    </form>
  );
}
