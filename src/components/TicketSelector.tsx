"use client";

import { TICKET_TIERS, TicketTier } from "@/lib/types";

interface TicketSelectorProps {
  selected: TicketTier | null;
  onSelect: (tier: TicketTier) => void;
}

function formatPrice(cents: number): string {
  return "$" + (cents / 100).toFixed(0);
}

export default function TicketSelector({
  selected,
  onSelect,
}: TicketSelectorProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {TICKET_TIERS.map((tier) => (
        <button
          key={tier.count}
          type="button"
          onClick={() => onSelect(tier)}
          className={`ticket-card text-left relative ${
            selected?.count === tier.count ? "selected" : ""
          }`}
        >
          {/* Savings badge */}
          {tier.savings && (
            <span className="absolute -top-3 -right-2 bg-gradient-to-r from-[#823530] to-[#9A3D36] text-[#E8D8BC] text-xs font-bold px-3 py-1 rounded-full">
              {tier.savings}
            </span>
          )}

          <div className="flex justify-between items-center mb-2">
            <span className="text-xl font-bold text-[#823530]">
              {tier.label}
            </span>
            <span className="text-2xl font-extrabold text-[#1E3050]">
              {formatPrice(tier.price)}
            </span>
          </div>

          

          {/* Selection indicator */}
          {selected?.count === tier.count && (
            <div className="absolute top-3 left-3">
              <svg
                className="w-6 h-6 text-[#823530]"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
          )}
        </button>
      ))}
    </div>
  );
}
