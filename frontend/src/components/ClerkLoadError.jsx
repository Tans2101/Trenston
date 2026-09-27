export default function ClerkLoadError({ onRetry }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-helm-bg p-8 text-center">
      <p className="text-lg text-helm-fg mb-2">Sign-in service is not responding</p>
      <p className="text-sm text-helm-muted max-w-lg leading-relaxed">
        DNS is verified, but Clerk SSL may still be deploying. In{" "}
        <a href="https://dashboard.clerk.com/~/domains" className="text-helm-gold hover:underline" target="_blank" rel="noreferrer">
          Clerk Dashboard → Domains
        </a>
        , confirm <span className="font-mono text-xs">SSL Certificates</span> show green for{" "}
        <span className="font-mono text-xs">Frontend API</span> and{" "}
        <span className="font-mono text-xs">Account portal</span>. If a{" "}
        <span className="text-helm-fg">Deploy certificates</span> button appears, click it.
        Then hard-refresh this page.
      </p>
      <button
        type="button"
        className="mt-6 rounded-lg bg-helm-gold text-helm-navy px-4 py-2 text-sm font-medium"
        onClick={onRetry || (() => window.location.reload())}
      >
        Retry
      </button>
    </div>
  );
}
