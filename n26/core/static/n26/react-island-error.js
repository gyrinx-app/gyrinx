// Cotton supplies the alert so recovery does not depend on a working React bundle.
export function showIslandError(host, target, retry, kind = "load") {
    const source = document.getElementById(
        host.dataset.reactError || "n26-react-error",
    );
    const content = source?.content.cloneNode(true);
    const message =
        kind === "load"
            ? "Gyrinx could not load this section. Check your connection and try again."
            : "This section stopped working. Try again, or reload the page if the problem continues.";
    if (!content) {
        const alert = document.createElement("p");
        alert.setAttribute("role", "alert");
        alert.textContent = message;
        target.replaceChildren(alert);
        return;
    }
    content.querySelector("[data-react-error-message]").textContent = message;
    content.querySelector("[data-react-reload]").href = window.location.href;
    const button = content.querySelector("[data-react-retry]");
    const spinner = content.querySelector("[data-react-retry-spinner]");
    button.addEventListener("click", () => {
        if (button.disabled || !host.isConnected) return;
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        spinner.hidden = false;
        retry();
    });
    target.replaceChildren(content);
}
