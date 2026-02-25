import Link from "next/link";

const VENMO_USERNAME = "Sir-Pork-A-Lot";

interface SuccessPageProps {
  searchParams: Promise<{
    amount?: string;
    tickets?: string;
    name?: string;
  }>;
}

export default async function SuccessPage({ searchParams }: SuccessPageProps) {
  const params = await searchParams;
  const amountCents = params.amount ? parseInt(params.amount) : null;
  const amountDollars = amountCents ? (amountCents / 100).toFixed(2) : null;
  const tickets = params.tickets ? parseInt(params.tickets) : null;
  const name = params.name ?? null;

  // Build the Venmo URL here to avoid double-encoding through query params
  const venmoUrl =
    tickets && amountDollars && name
      ? `https://venmo.com/${VENMO_USERNAME}?txn=pay&amount=${amountDollars}&note=${encodeURIComponent(
          `Hogs for the Cause 2026 - ${tickets} Raffle Ticket${
            tickets > 1 ? "s" : ""
          } (${name})`
        )}`
      : null;

  const hasOrderDetails = tickets && amountDollars && name && venmoUrl;

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center">
        <div className="text-8xl mb-6">🎟️</div>
        <h1 className="text-4xl font-extrabold mb-4">
          <span className="bg-gradient-to-r from-[#823530] via-[#9A3D36] to-[#823530] bg-clip-text text-transparent">
            {hasOrderDetails ? "One Last Step!" : "Thank You!"}
          </span>
        </h1>

        {hasOrderDetails ? (
          <>
            <p className="text-lg text-[#2B3E5C]/80 mb-2">
              Hi <strong>{name}</strong> — your order for{" "}
              <strong>
                {tickets} ticket{tickets > 1 ? "s" : ""}
              </strong>{" "}
              is reserved!
            </p>
            <p className="text-[#2B3E5C]/60 mb-6">
              To confirm your entry, send{" "}
              <strong className="text-[#823530] text-xl">${amountDollars}</strong>{" "}
              to <strong className="text-[#823530]">@Sir-Pork-A-Lot</strong> on Venmo.
              The note is pre-filled for you.
            </p>

            {/* Venmo CTA Button */}
            <a
              href={venmoUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-3 bg-[#3D95CE] hover:bg-[#2d7faf] active:bg-[#2370a0] text-white font-bold text-lg px-8 py-4 rounded-2xl transition-colors w-full mb-4 shadow-lg"
            >
              {/* Venmo "V" wordmark path */}
              <svg
                viewBox="0 0 300 300"
                className="w-7 h-7 fill-white"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path d="M246.5 25c8.3 13.7 12 27.8 12 45.6 0 56.8-48.4 130.5-87.6 182.3h-88.3L44 28.8l75.7-7.2 19.7 158.5c18.3-29.7 41-76.6 41-108.4 0-17.5-3-29.5-7.8-39.2L246.5 25z" />
              </svg>
              Pay ${amountDollars} with Venmo
            </a>

            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-8 text-sm text-amber-800 text-left">
              <p className="font-semibold mb-1">💡 How it works</p>
              <ol className="list-decimal list-inside space-y-1">
                <li>Tap the button above to open Venmo.</li>
                <li>The amount &amp; note are pre-filled — just hit Pay.</li>
                <li>Your entry is confirmed once payment is received.</li>
              </ol>
            </div>
          </>
        ) : (
          <>
            <p className="text-lg text-[#2B3E5C]/80 mb-2">
              Your raffle ticket order has been received!
            </p>
            <p className="text-[#2B3E5C]/60 mb-8">
              Thank you for supporting{" "}
              <strong className="text-[#823530]">Team Sir Pork a Lot</strong> at
              Hogs for the Cause 2026!
            </p>
          </>
        )}

        <div className="divider-flame mb-8 mx-auto max-w-xs" />
        <div className="text-6xl mb-6">🐷🔥</div>
        <Link href="/" className="btn-fire inline-block">
          Back to Home
        </Link>
      </div>
    </div>
  );
}
