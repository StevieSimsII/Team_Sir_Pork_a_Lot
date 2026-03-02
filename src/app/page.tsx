import Image from "next/image";
import EmberParticles from "@/components/EmberParticles";
import PurchaseForm from "@/components/PurchaseForm";
import PrizesAccordion from "@/components/PrizesAccordion";

export default function Home() {
  return (
    <>
      <EmberParticles />
      <div className="relative z-10 neon-bg">
        {/* Hero Section */}
        <header className="text-center pt-10 pb-6 px-4">
          <div className="max-w-3xl mx-auto">
            {/* Logo */}
            <div className="flex justify-center mb-4">
              <Image
                src="/sir-pork-a-lot.png"
                alt="Sir Pork-a-Lot"
                width={220}
                height={220}
                className="drop-shadow-[0_0_35px_rgba(255,0,204,0.55)]"
                priority
              />
            </div>
            <p className="text-lg sm:text-xl text-[#c084fc] font-semibold tracking-widest uppercase">
              Hogs for the Cause 2026
            </p>
            <div className="divider-neon mt-5 mx-auto max-w-xs" />
          </div>
        </header>

        {/* Raffle Info */}
        <section className="max-w-2xl mx-auto px-4 pb-4 text-center">
          <h2 className="text-3xl font-bold mb-3 text-[#00e5ff] drop-shadow-[0_0_10px_rgba(0,229,255,0.5)]">
            🎟️ Raffle Ticket Sale 🎟️
          </h2>
          <p className="text-base text-[#a78bca] max-w-xl mx-auto">
            Support <strong className="text-[#ff00cc]">Team Sir Pork a Lot</strong>{" "}
            by purchasing raffle tickets! Amazing prizes await.
          </p>
        </section>

        {/* Prizes Accordion */}
        <section className="max-w-2xl mx-auto px-4 pb-4">
          <PrizesAccordion />
        </section>

        {/* Purchase Form Section */}
        <section className="max-w-2xl mx-auto px-4 pb-16 pt-4">
          <div className="bg-[#1a0f35]/60 backdrop-blur-sm rounded-2xl p-6 sm:p-8 border border-[#c084fc]/20 shadow-[0_0_40px_rgba(192,132,252,0.1)]">
            <PurchaseForm />
          </div>
        </section>

        {/* Footer */}
        <footer className="text-center py-8 text-sm text-[#a78bca]/50 border-t border-[#c084fc]/10">
          <p>&copy; 2026 Team Sir Pork a Lot — Hogs for the Cause</p>
        </footer>
      </div>
    </>
  );
}
