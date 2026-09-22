import { Component } from "react";
import TrenstonMark from "@/components/HelmMark";

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

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-helm-bg grain p-6">
          <div className="relative z-10 max-w-md w-full text-center">
            <TrenstonMark size={48} className="rounded-md mx-auto mb-6" />
            <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-gold mb-3">Something went wrong</p>
            <h1 className="font-display text-2xl font-normal text-helm-fg tracking-tight">This screen hit an unexpected error.</h1>
            <p className="text-sm text-helm-muted mt-3 leading-relaxed">
              You can try again. If it keeps happening, refresh the page or sign back in.
            </p>
            <button
              data-testid="error-retry-btn"
              onClick={this.retry}
              className="mt-8 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-5 py-2.5 transition-colors hover:bg-helm-gold-hover"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
