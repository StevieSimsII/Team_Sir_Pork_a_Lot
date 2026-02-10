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
              <span className="bg-gradient-to-r from-[#823530] via-[#9A3D36] to-[#823530] bg-clip-text text-transparent">
                Sir Pork a Lot
              </span>
            </h1>
            <p className="text-xl sm:text-2xl text-[#2B3E5C] font-semibold mt-2">
              Hogs for the Cause 2026
            </p>
            <div className="divider-flame mt-6 mx-auto max-w-xs" />
          </div>
        </header>

        {/* Raffle Info */}
        <section className="max-w-2xl mx-auto px-4 pb-4 text-center">
          <h2 className="text-3xl font-bold mb-3 text-[#2B3E5C]">
            🔥 Raffle Ticket Sale 🔥
          </h2>
          <p className="text-lg text-[#2B3E5C]/70 max-w-xl mx-auto">
            Support <strong className="text-[#823530]">Team Sir Pork a Lot</strong>{" "}
            by purchasing raffle tickets! Amazing prizes await — the more tickets
            you grab, the more you save!
          </p>
        </section>

        {/* Purchase Form Section */}
        <section className="max-w-2xl mx-auto px-4 pb-16 pt-4">
          <div className="bg-white/30 backdrop-blur-sm rounded-2xl p-6 sm:p-8 border border-[#2B3E5C]/10 shadow-xl">
            <PurchaseForm />
          </div>
        </section>

        {/* Footer */}
        <footer className="text-center py-8 text-sm text-[#2B3E5C]/50 border-t border-[#2B3E5C]/10">
          <p>
            &copy; 2026 Team Sir Pork a Lot — Hogs for the Cause
          </p>
        </footer>
      </div>
    </>
  );
}
