import { Component, ErrorInfo, ReactNode } from "react";

interface Props { children: ReactNode; fallback: (error: Error, reset: () => void) => ReactNode }
interface State { error: Error | null }

/** Contains a render error to the current page so the sidebar and navigation keep working.
 *  Re-mounted per route (keyed by pathname in App), so leaving the page clears the error. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("SkillRadar page error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) return this.props.fallback(this.state.error, () => this.setState({ error: null }));
    return this.props.children;
  }
}
