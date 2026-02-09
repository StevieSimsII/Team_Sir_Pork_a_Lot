import EmberParticles from "@/components/EmberParticles";
import PurchaseForm from "@/components/PurchaseForm";

export default function Home() {
  return (
    <>
      <EmberParticles />
      <div className="relative z-10 min-h-screen">
        {/* Hero Section */}
        <header className="text-center pt-12 pb-8 px-4">
          <div className="max-w-3xl mx-auto">
            {/* Logo / pig icon */}
            <div className="text-7xl mb-4">🐷</div>
            <h1 className="text-5xl sm:text-6xl font-extrabold tracking-tight mb-2">
              <span className="bg-gradient-to-r from-[#8B2500] via-[#D2691E] to-[#DAA520] bg-clip-text text-transparent">
                Team Sir Pork a Lot
              </span>
            </h1>
            <p className="text-xl sm:text-2xl text-[#DAA520] font-semibold mt-2">
              Hogs for the Cause 2026
            </p>
            <div className="divider-flame mt-6 mx-auto max-w-xs" />
          </div>
        </header>

        {/* Raffle Info */}
        <section className="max-w-2xl mx-auto px-4 pb-4 text-center">
          <h2 className="text-3xl font-bold mb-3 text-white">
            🔥 Raffle Ticket Sale 🔥
          </h2>
          <p className="text-lg text-[#FFF8DC]/70 max-w-xl mx-auto">
            Support <strong className="text-[#DAA520]">Team Sir Pork a Lot</strong>{" "}
            by purchasing raffle tickets! Amazing prizes await — the more tickets
            you grab, the more you save!
          </p>
        </section>

        {/* Purchase Form Section */}
        <section className="max-w-2xl mx-auto px-4 pb-16 pt-4">
          <div className="bg-gradient-to-b from-[#2d1810]/80 to-[#1a0a00]/90 rounded-2xl p-6 sm:p-8 border border-[#DAA520]/10 shadow-2xl">
            <PurchaseForm />
          </div>
        </section>

        {/* Footer */}
        <footer className="text-center py-8 text-sm text-[#FFF8DC]/40 border-t border-[#DAA520]/10">
          <p>
            &copy; 2026 Team Sir Pork a Lot — Hogs for the Cause
          </p>
        </footer>
      </div>
    </>
  );
}
