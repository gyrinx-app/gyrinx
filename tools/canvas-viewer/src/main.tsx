import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Viewer } from "./viewer";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
    throw new Error("Canvas viewer root is missing.");
}

createRoot(root).render(
    <StrictMode>
        <Viewer />
    </StrictMode>,
);
