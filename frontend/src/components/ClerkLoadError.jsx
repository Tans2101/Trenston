export default function ClerkLoadError({ onRetry }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-helm-bg p-8 text-center">
      <p className="text-lg text-helm-fg mb-2">Sign-in service is not responding</p>
      <p className="text-sm text-helm-muted max-w-md leading-relaxed">
        We could not reach the sign-in service. Check your connection and try again. If it keeps happening, email{" "}
        <a href="mailto:contact@trenston.com" className="text-helm-gold hover:underline">contact@trenston.com</a>.
      </p>
      <button
        type="button"
        className="mt-6 rounded-lg bg-helm-fg text-helm-bg px-4 py-2 text-sm font-medium"
        onClick={onRetry || (() => window.location.reload())}
      >
        Retry
      </button>
    </div>
  );
}
