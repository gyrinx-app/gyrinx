// Django owns each host. React owns only the host's children.
const islands = new Map();

export function mountWithin(scope, loadModule = (url) => import(url)) {
    const hosts = [...scope.querySelectorAll("[data-react-module]")];
    if (scope.matches?.("[data-react-module]")) hosts.unshift(scope);
    for (const host of hosts) {
        if (islands.has(host)) continue;
        const pending = { dispose: null };
        islands.set(host, pending);
        loadModule(host.dataset.reactModule)
            .then((module) => {
                if (!host.isConnected || islands.get(host) !== pending) return;
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
                host.replaceChildren();
                const message = document.createElement("p");
                message.setAttribute("role", "alert");
                message.textContent = "This section could not load. ";
                const retry = document.createElement("a");
                retry.href = window.location.href;
                retry.className = "underline";
                retry.textContent = "Reload the page";
                message.append(retry, ".");
                host.append(message);
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

// Alpine x-if inserts a host only when a closed row opens. That is not an
// htmx swap, so the first paint and htmx:load never see it.
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
