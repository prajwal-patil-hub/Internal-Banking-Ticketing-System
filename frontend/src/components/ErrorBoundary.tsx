import { Component, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface State { error: Error | null }

/**
 * Top-level error boundary. Without this, any uncaught render error in any
 * route blanks the entire page (React 18 unmounts the tree on error).
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }): void {
    console.error('[ErrorBoundary] caught', error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="min-h-screen grid place-items-center p-8">
        <div className="glass-strong max-w-lg w-full rounded-4xl p-8 text-center">
          <div className="mx-auto h-12 w-12 rounded-2xl grid place-items-center mb-4 bg-danger-soft">
            <AlertTriangle className="h-6 w-6 text-danger-deep" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink mb-2">
            Something went wrong.
          </h1>
          <p className="text-sm text-ink-muted mb-5">
            The app hit an unexpected error while rendering this page.
          </p>
          <pre className="text-xs text-left bg-white/70 border border-white/50 p-3 rounded-2xl overflow-auto max-h-40 text-ink-muted">
            {this.state.error.message}
          </pre>
          <button onClick={this.reset} className="btn-primary mt-5 w-full">
            Try again
          </button>
        </div>
      </div>
    );
  }
}
