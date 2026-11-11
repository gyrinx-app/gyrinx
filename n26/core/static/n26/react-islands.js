// Django manages each host element; React manages its children.
import { showIslandError } from "./react-island-error.js";

const islands = new Map();
let retrySequence = 0;

export function mountWithin(
    scope,
    loadModule = (url) => import(url),
    attempt = 0,
) {
    const hosts = [...scope.querySelectorAll("[data-react-module]")];
    if (scope.matches?.("[data-react-module]")) hosts.unshift(scope);
    for (const host of hosts) {
        if (islands.has(host)) continue;
        const pending = { dispose: null };
        islands.set(host, pending);
        let url = host.dataset.reactModule;
        if (attempt) {
            const fresh = new URL(url, window.location.href);
            // Browsers cache failed module imports; retry only the entry URL.
            fresh.searchParams.set("retry", String(++retrySequence));
            url = fresh.href;
        }
        let imported = false;
        loadModule(url)
            .then((module) => {
                if (!host.isConnected || islands.get(host) !== pending) return;
                imported = true;
                const data = document.getElementById(host.dataset.reactProps);
                pending.dispose = module.mount(
                    host,
                    JSON.parse(data.textContent),
                );
            })
            .catch((error) => {
                if (!host.isConnected || islands.get(host) !== pending) return;
                if (host.hasAttribute("data-react-fallback")) {
                    console.error("React island failed to load", error);
                    return;
                }
                showIslandError(
                    host,
                    host,
                    () => {
                        if (islands.get(host) !== pending) return;
                        islands.delete(host);
                        mountWithin(host, loadModule, attempt + 1);
                    },
                    imported ? "render" : attempt ? "reload" : "load",
                );
                console.error("React island failed to load", error);
            });
    }
}

function release(node) {
    if (!(node instanceof Element)) return;
    const hosts = [...node.querySelectorAll("[data-react-module]")];
    if (node.matches("[data-react-module]")) hosts.unshift(node);
    for (const host of hosts) {
        const mounted = islands.get(host);
        if (!mounted) continue;
        islands.delete(host);
        mounted.dispose?.();
    }
}

// Alpine x-if can insert island hosts outside the initial scan and htmx updates.
export function watchInsertions(root) {
    const observer = new MutationObserver((records) => {
        for (const record of records) {
            for (const node of record.addedNodes) {
                if (node instanceof Element) mountWithin(node);
            }
            for (const node of record.removedNodes) release(node);
        }
    });
    observer.observe(root, { childList: true, subtree: true });
    return observer;
}

document.addEventListener("htmx:load", (event) =>
    mountWithin(event.detail.elt),
);
document.addEventListener("htmx:beforeCleanupElement", (event) => {
    release(event.detail.elt);
});
mountWithin(document);
export const pageInsertions = document.body
    ? watchInsertions(document.body)
    : null;
