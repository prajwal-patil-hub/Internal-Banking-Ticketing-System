import { Component, type ReactNode } from 'react';

interface State { error: Error | null }

/**
 * Top-level error boundary. Without this, any uncaught render error in any
 * route blanks the entire page (React 18 unmounts the tree on error).
 *
 * Catches once per render cycle. The "Try again" button forces a remount of
 * the children by bumping a key — most transient errors (a stale
 * useQuery cache, a malformed prop) clear on retry.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }): void {
    // Surface the error to the dev console with structure.
    console.error('[ErrorBoundary] caught', error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="min-h-full flex items-center justify-center p-8 bg-surface-muted dark:bg-slate-950">
        <div className="max-w-lg w-full bg-surface dark:bg-slate-900 rounded-2xl shadow-card p-8 text-center">
          <div className="text-3xl mb-2">⚠️</div>
          <h1 className="text-xl font-semibold mb-2">Something went wrong.</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
            The app hit an unexpected error while rendering this page.
          </p>
          <pre className="text-xs text-left bg-surface-muted dark:bg-slate-800 p-3 rounded-xl overflow-auto max-h-40">
            {this.state.error.message}
          </pre>
          <button onClick={this.reset} className="btn-primary mt-4">Try again</button>
        </div>
      </div>
    );
  }
}
