import {
    Component,
    type ComponentType,
    type ErrorInfo,
    type ReactNode,
    useCallback,
    useEffect,
    useMemo,
    useState,
} from "react";

import type { CanvasEntry } from "./canvas-directory";

type CanvasResponse = {
    canvasDirectory: string;
    canvases: CanvasEntry[];
};

type CanvasAction = {
    type: string;
    path?: string;
    selection?: { startLineNumber?: number };
};

declare global {
    interface Window {
        __canvasViewerCanvasId?: string;
    }
    interface WindowEventMap {
        "canvas-viewer-action": CustomEvent<CanvasAction>;
    }
}

class CanvasErrorBoundary extends Component<
    { children: ReactNode; resetKey: string },
    { error: Error | null }
> {
    state = { error: null as Error | null };

    static getDerivedStateFromError(error: Error) {
        return { error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error("Canvas render failed", error, info);
    }

    componentDidUpdate(previous: { resetKey: string }) {
        if (previous.resetKey !== this.props.resetKey && this.state.error) {
            this.setState({ error: null });
        }
    }

    render() {
        if (this.state.error) {
            return (
                <div
                    className="viewer-message viewer-message-danger"
                    role="alert"
                >
                    <strong>The Canvas could not render.</strong>
                    <pre>{this.state.error.message}</pre>
                </div>
            );
        }
        return this.props.children;
    }
}

async function fetchCanvases(): Promise<CanvasResponse> {
    const response = await fetch("/api/canvases", { cache: "no-store" });
    if (!response.ok) {
        throw new Error(`Canvas list returned ${response.status}.`);
    }
    return response.json() as Promise<CanvasResponse>;
}

export function Viewer() {
    const [directory, setDirectory] = useState("");
    const [canvases, setCanvases] = useState<CanvasEntry[]>([]);
    const [selectedName, setSelectedName] = useState(
        () => new URLSearchParams(window.location.search).get("canvas") ?? "",
    );
    const [Canvas, setCanvas] = useState<ComponentType | null>(null);
    const [error, setError] = useState("");
    const [reload, setReload] = useState(0);
    const [action, setAction] = useState<CanvasAction | null>(null);

    const refreshList = useCallback(async () => {
        try {
            const data = await fetchCanvases();
            setDirectory(data.canvasDirectory);
            setCanvases(data.canvases);
            setSelectedName((current) => {
                if (data.canvases.some((canvas) => canvas.name === current)) {
                    return current;
                }
                return data.canvases[0]?.name ?? "";
            });
            setError("");
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : String(reason));
        }
    }, []);

    useEffect(() => {
        void refreshList();
    }, [refreshList]);

    useEffect(() => {
        const handleAction = (
            event: WindowEventMap["canvas-viewer-action"],
        ) => {
            setAction(event.detail);
        };
        window.addEventListener("canvas-viewer-action", handleAction);
        return () =>
            window.removeEventListener("canvas-viewer-action", handleAction);
    }, []);

    const selected = useMemo(
        () => canvases.find((canvas) => canvas.name === selectedName) ?? null,
        [canvases, selectedName],
    );

    useEffect(() => {
        if (!selected) {
            setCanvas(null);
            return;
        }

        let cancelled = false;
        setCanvas(null);
        setError("");
        setAction(null);
        window.__canvasViewerCanvasId = selected.name;
        const moduleUrl = `${selected.moduleUrl}?v=${selected.mtimeMs}-${reload}`;

        void import(/* @vite-ignore */ moduleUrl)
            .then((module: { default?: ComponentType }) => {
                if (cancelled) return;
                if (typeof module.default !== "function") {
                    throw new Error(
                        "The Canvas must default-export a React component.",
                    );
                }
                setCanvas(() => module.default as ComponentType);
            })
            .catch((reason: unknown) => {
                if (!cancelled) {
                    setError(
                        reason instanceof Error
                            ? reason.message
                            : String(reason),
                    );
                }
            });

        const query = new URLSearchParams(window.location.search);
        query.set("canvas", selected.name);
        window.history.replaceState(null, "", `?${query.toString()}`);
        return () => {
            cancelled = true;
        };
    }, [selected, reload]);

    const copyActionPath = async () => {
        if (!action?.path) return;
        const line = action.selection?.startLineNumber;
        await navigator.clipboard.writeText(
            line ? `${action.path}:${line}` : action.path,
        );
    };

    return (
        <div className="viewer-shell">
            <header className="viewer-toolbar">
                <div className="viewer-toolbar-title">
                    <strong>Canvas viewer</strong>
                    <span>{canvases.length} files</span>
                </div>
                <label className="viewer-picker" htmlFor="canvas-picker">
                    <span>Canvas</span>
                    <select
                        id="canvas-picker"
                        value={selectedName}
                        onChange={(event) =>
                            setSelectedName(event.target.value)
                        }
                        disabled={canvases.length === 0}
                    >
                        {canvases.map((canvas) => (
                            <option key={canvas.name} value={canvas.name}>
                                {canvas.name}
                            </option>
                        ))}
                    </select>
                </label>
                <button
                    type="button"
                    onClick={() => setReload((value) => value + 1)}
                >
                    Reload
                </button>
            </header>

            <div className="viewer-source" title={selected?.path ?? directory}>
                {selected?.path ?? directory}
            </div>

            {action && (
                <div className="viewer-action" role="status">
                    <span>
                        {action.type === "openFile" && action.path
                            ? `Open this file in your editor: ${action.path}${action.selection?.startLineNumber ? `:${action.selection.startLineNumber}` : ""}.`
                            : `The local viewer cannot run the ${action.type} host action.`}
                    </span>
                    {action.path && (
                        <button
                            type="button"
                            onClick={() => void copyActionPath()}
                        >
                            Copy path
                        </button>
                    )}
                    <button type="button" onClick={() => setAction(null)}>
                        Dismiss
                    </button>
                </div>
            )}

            <main className="viewer-canvas">
                {error ? (
                    <div
                        className="viewer-message viewer-message-danger"
                        role="alert"
                    >
                        <strong>The Canvas could not load.</strong>
                        <pre>{error}</pre>
                    </div>
                ) : Canvas && selected ? (
                    <CanvasErrorBoundary
                        resetKey={`${selected.name}-${reload}`}
                    >
                        <Canvas />
                    </CanvasErrorBoundary>
                ) : canvases.length === 0 ? (
                    <div className="viewer-message">
                        <strong>No Canvas files found.</strong>
                        <p>
                            Save a <code>.canvas.tsx</code> file in {directory}.
                        </p>
                    </div>
                ) : (
                    <div className="viewer-message">Loading Canvas…</div>
                )}
            </main>
        </div>
    );
}
