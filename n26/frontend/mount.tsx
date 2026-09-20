import { Component, type ComponentType, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

class IslandError extends Component<
    { children: ReactNode },
    { failed: boolean }
> {
    state = { failed: false };
    static getDerivedStateFromError() {
        return { failed: true };
    }
    render() {
        return this.state.failed ? (
            <p role="alert">
                This section could not load.{" "}
                <a className="underline" href={window.location.href}>
                    Reload the page
                </a>
                .
            </p>
        ) : (
            this.props.children
        );
    }
}

export function mount<P extends object>(
    element: HTMLElement,
    View: ComponentType<P>,
    props: P,
) {
    const root = createRoot(element, { identifierPrefix: `${element.id}-` });
    root.render(
        <IslandError>
            <View {...props} />
        </IslandError>,
    );
    return () => root.unmount();
}
