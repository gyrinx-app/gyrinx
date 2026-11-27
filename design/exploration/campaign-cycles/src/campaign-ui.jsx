import React from "react";
import { Button } from "./controls.jsx";
import { Modal as SharedModal, Input } from "./surface-controls.jsx";
import cotton from "./cotton.json";
import { Cotton } from "./campaign-cotton.jsx";
import { outcomeLabels } from "./campaign-model.js";
export const ErrorContext = React.createContext("");
export function Modal({ children, ...props }) {
    const error = React.useContext(ErrorContext);
    return (
        <SharedModal {...props}>
            {children}
            {error && (
                <p className="cp-dialog-error cp-error" role="alert">
                    {error}
                </p>
            )}
        </SharedModal>
    );
}
export const copy = (x) => structuredClone(x);
export const gangName = (s, id) =>
    s.gangs.find((g) => g.id === id)?.name || "Unknown gang";
export const cycleOptions = (s) =>
    s.cycles.map((c) => [
        c.id,
        `${c.name}${s.closedCycles.includes(c.id) ? " · ended" : ""}`,
    ]);
export const phaseOptions = (s) => s.phases.map((p) => [p.id, p.name]);
export const fmt = (n) => Number(n).toLocaleString("en-GB");
export function TextArea({ label, value, onChange, help, ...props }) {
    return (
        <label className="history-field">
            <span className={cotton.label}>{label}</span>
            <textarea
                aria-label={label}
                className={cotton.textarea}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                {...props}
            />
            {help && <span className="cp-help">{help}</span>}
        </label>
    );
}
export function CheckField({ label, checked, onChange }) {
    return (
        <label className="cp-check">
            <input
                type="checkbox"
                checked={checked}
                onChange={(e) => onChange(e.target.checked)}
            />
            <span>{label}</span>
        </label>
    );
}
export function FormFoot({ onClose, label = "Save", children }) {
    return (
        <footer>
            <Button variant="default" onClick={onClose}>
                Cancel
            </Button>
            {children}
            <Button variant="success" type="submit">
                {label}
            </Button>
        </footer>
    );
}
export function Tag({ children, active = false }) {
    return (
        <Cotton
            name={active ? "activeBadge" : "badge"}
            bindings={{ BADGE_TEXT: children }}
        />
    );
}
export function RewardTable({ phase, editable = false, onChange }) {
    return (
        <div className="cp-rewards">
            <Cotton
                name="table"
                slots={{
                    content: (
                        <>
                            <thead>
                                <tr>
                                    <th>Outcome</th>
                                    <th>Credits</th>
                                    <th>Reputation</th>
                                </tr>
                            </thead>
                            <tbody>
                                {Object.entries(outcomeLabels).map(
                                    ([key, label]) => (
                                        <tr key={key}>
                                            <td>{label}</td>
                                            <td>
                                                {editable ? (
                                                    <Input
                                                        label={`${label} credits`}
                                                        value={
                                                            phase.rewards[key]
                                                                .credits
                                                        }
                                                        onChange={(credits) =>
                                                            onChange(key, {
                                                                ...phase
                                                                    .rewards[
                                                                    key
                                                                ],
                                                                credits,
                                                            })
                                                        }
                                                        required
                                                        maxLength={20}
                                                    />
                                                ) : (
                                                    <span className="cp-formula">
                                                        {
                                                            phase.rewards[key]
                                                                .credits
                                                        }
                                                        ¢
                                                    </span>
                                                )}
                                            </td>
                                            <td>
                                                {editable ? (
                                                    <Input
                                                        label={`${label} reputation`}
                                                        value={
                                                            phase.rewards[key]
                                                                .reputation
                                                        }
                                                        onChange={(
                                                            reputation,
                                                        ) =>
                                                            onChange(key, {
                                                                ...phase
                                                                    .rewards[
                                                                    key
                                                                ],
                                                                reputation,
                                                            })
                                                        }
                                                        type="number"
                                                        min="-1000"
                                                        max="1000"
                                                        required
                                                    />
                                                ) : (
                                                    <span>
                                                        {Number(
                                                            phase.rewards[key]
                                                                .reputation,
                                                        ) > 0
                                                            ? "+"
                                                            : ""}
                                                        {
                                                            phase.rewards[key]
                                                                .reputation
                                                        }
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    ),
                                )}
                            </tbody>
                        </>
                    ),
                }}
            />
        </div>
    );
}

export function IconAction({ icon, label, reason, ...props }) {
    return (
        <Button
            icon={icon}
            aria-label={label}
            title={reason || label}
            disabled={!!reason}
            {...props}
        />
    );
}
