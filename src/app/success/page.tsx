import Link from "next/link";

export default function SuccessPage() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center">
        <div className="text-8xl mb-6">🎉</div>
        <h1 className="text-4xl font-extrabold mb-4">
          <span className="bg-gradient-to-r from-[#823530] via-[#9A3D36] to-[#823530] bg-clip-text text-transparent">
            Thank You!
          </span>
        </h1>
        <p className="text-lg text-[#2B3E5C]/80 mb-2">
          Your raffle ticket purchase was successful!
        </p>
        <p className="text-[#2B3E5C]/60 mb-8">
          A confirmation will be sent to your email. Good luck and thank you for
          supporting <strong className="text-[#823530]">Team Sir Pork a Lot</strong> at
          Hogs for the Cause 2026!
        </p>
        <div className="divider-flame mb-8 mx-auto max-w-xs" />
        <div className="text-6xl mb-6">🐷🔥</div>
        <Link href="/" className="btn-fire inline-block">
          Back to Home
        </Link>
      </div>
    </div>
  );
}
