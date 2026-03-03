"use client";

import { useState } from "react";

const prizes = [
  { icon: "🚗", name: "Vivid EV V4L Golf Cart" },
  { icon: "🍕", name: "Ooni Karu 2 Pro Multi Fuel Pizza Oven" },
  { icon: "🏙️", name: "Warehouse District Penthouse & Besh GC – Weekend Stay" },
  { icon: "🏝️", name: "3 Night Stay at Grand Isle – Bayside" },
  { icon: "🧊", name: "Yeti Haul" },
  { icon: "🥤", name: "Yeti Soft Cooler + Tumblers" },
  { icon: "🔊", name: "Turtlebox Speaker" },
  { icon: "🥩", name: "McCord's Gift Card + Cutting Board" },
  { icon: "🎁", name: "Martin's Gift Card, Lola Blanket + Hogs for the Cause door hanger by Home Malone" },
];

export default function PrizesAccordion() {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl overflow-hidden border border-[#ffd700]/30 shadow-[0_0_20px_rgba(255,215,0,0.08)]">
      {/* Header / toggle */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-4 bg-[#1a0f35]/80 hover:bg-[#1a0f35] transition-colors"
        aria-expanded={open}
      >
        <span className="text-lg font-bold text-[#ffd700] drop-shadow-[0_0_8px_rgba(255,215,0,0.7)] flex items-center gap-2">
          🏆 See the Prizes
        </span>
        <svg
          className={`w-5 h-5 text-[#ffd700] transition-transform duration-300 ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Prize grid */}
      {open && (
        <div className="px-5 pb-5 pt-4 bg-[#0f0820]/70 flex flex-col gap-3">
          {prizes.map((prize, i) => (
            <div
              key={i}
              className="flex items-start gap-3 p-3 rounded-lg bg-[#1a0f35]/60 border border-[#c084fc]/20 hover:border-[#c084fc]/50 transition-colors"
            >
              <span className="text-2xl leading-none flex-shrink-0 mt-0.5">{prize.icon}</span>
              <span className="text-sm text-[#f0e6ff] leading-snug">{prize.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
