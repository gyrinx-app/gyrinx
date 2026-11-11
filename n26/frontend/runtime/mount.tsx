import { Component, type ComponentType, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { showIslandError } from "../../core/static/n26/react-island-error.js";

class IslandError extends Component<
    { children: ReactNode; element: HTMLElement },
    { failed: boolean }
> {
    state = { failed: false };
    static getDerivedStateFromError() {
        return { failed: true };
    }
    render() {
        return this.state.failed ? (
            <div
                ref={(target) => {
                    if (target)
                        showIslandError(
                            this.props.element,
                            target,
                            () => this.setState({ failed: false }),
                            "render",
                        );
                }}
            />
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
        <IslandError element={element}>
            <View {...props} />
        </IslandError>,
    );
    return () => root.unmount();
}
