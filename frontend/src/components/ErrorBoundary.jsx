import { Component } from "react";
import TrenstonMark from "@/components/HelmMark";
import { isChunkLoadError, isOffline } from "@/lib/chunkReload";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Trenston render error:", error, info);
  }

  retry = () => {
    this.setState({ error: null });
  };

  reload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.error) {
      // React.lazy caches a failed chunk load, so "Try again" cannot recover; only a reload can.
      const chunkFailed = isChunkLoadError(this.state.error);
      const offline = chunkFailed && isOffline();
      const updated = chunkFailed && !offline;
      return (
        <div className="min-h-screen flex items-center justify-center bg-helm-bg p-6">
          <div className="relative z-10 max-w-md w-full text-center">
            <TrenstonMark size={48} className="rounded-md mx-auto mb-6" />
            <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-gold mb-3">
              {offline ? "You're offline" : updated ? "Update available" : "Something went wrong"}
            </p>
            <h1 className="font-display text-2xl font-normal text-helm-fg tracking-tight">
              {offline
                ? "This page needs a connection to open."
                : updated
                  ? "Trenston was just updated."
                  : "This screen hit an unexpected error."}
            </h1>
            <p className="text-sm text-helm-muted mt-3 leading-relaxed">
              {offline
                ? "Reconnect to the internet, then reload. Anything you already saved is safe."
                : updated
                ? "Reload to get the latest version. Anything you already saved is safe."
                : "You can try again. If it keeps happening, reload the page or sign back in."}
            </p>
            <div className="mt-8 flex items-center justify-center gap-3">
              {chunkFailed ? (
                <button
                  type="button"
                  data-testid="error-reload-btn"
                  onClick={this.reload}
                  className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-5 py-2.5 transition-colors hover:bg-helm-gold-hover"
                >
                  Reload
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    data-testid="error-retry-btn"
                    onClick={this.retry}
                    className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-5 py-2.5 transition-colors hover:bg-helm-gold-hover"
                  >
                    Try again
                  </button>
                  <button
                    type="button"
                    data-testid="error-reload-btn"
                    onClick={this.reload}
                    className="rounded-md border border-helm-line text-helm-fg text-sm px-5 py-2.5 transition-colors hover:bg-helm-fg/[0.04]"
                  >
                    Reload page
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
