import React, { createContext, useContext, useRef, useState } from "react";

const Session = createContext(null);
export function CardSession({ children }) {
    const values = useRef(new Map());
    return (
        <Session.Provider value={values.current}>{children}</Session.Provider>
    );
}

// A view change can move a card into a new row without ending its tab selection.
export function useCardSession(key, initial) {
    const session = useContext(Session);
    const [value, update] = useState(() =>
        session.has(key) ? session.get(key) : initial,
    );
    function setValue(next) {
        const previous = session.has(key) ? session.get(key) : value;
        const resolved = typeof next === "function" ? next(previous) : next;
        session.set(key, resolved);
        update(resolved);
    }
    return [value, setValue];
}
