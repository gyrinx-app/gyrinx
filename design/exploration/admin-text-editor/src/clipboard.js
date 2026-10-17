export async function writeBlockClipboard(html, text) {
    if (navigator.clipboard.write && window.ClipboardItem) {
        await navigator.clipboard.write([
            new ClipboardItem({
                "text/html": new Blob([html], { type: "text/html" }),
                "text/plain": new Blob([text], { type: "text/plain" }),
            }),
        ]);
    } else await navigator.clipboard.writeText(text);
}
