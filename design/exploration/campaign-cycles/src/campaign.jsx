import React, { useState, useRef } from "react";
import { createRoot } from "react-dom/client";
import { Plus, Swords, X, RotateCcw, CircleCheck } from "lucide-react";
import { Button, Icon } from "./controls.jsx";
import { Select } from "./surface-controls.jsx";
import cotton from "./cotton.json";
import * as M from "./campaign-model.js";
import {
    CampaignCard as Card,
    CampaignFrame,
    CampaignNavigation,
    CampaignSubpageHeader,
    CampaignDashboard,
    CampaignActivity,
    CampaignBattles as BattleList,
} from "./campaign-view.jsx";
import {
    ErrorContext,
    Modal,
    FormFoot,
    Tag,
    RewardTable,
    cycleOptions,
    gangName,
} from "./campaign-ui.jsx";
import {
    PhaseForm,
    CycleForm,
    SettingsForm,
    BattleForm,
    EndCycleForm,
} from "./campaign-forms.jsx";
import { CampaignSchedule } from "./campaign-schedule.jsx";
import {
    useCampaignState,
    useCampaignNavigation,
    useCampaignTheme,
} from "./campaign-state.js";
function App() {
    const { state, update, reset, persistError, storageBlocked } =
        useCampaignState();
    const [modal, setModal] = useState(null),
        [message, setMessage] = useState(""),
        [error, setError] = useState(""),
        [battleCycle, setBattleCycle] = useState("all");
    const closeGuard = useRef(null),
        saving = useRef(false);
    const close = (force = false) => {
        if (force !== true && saving.current) return false;
        if (force !== true && closeGuard.current && !closeGuard.current())
            return false;
        setModal(null);
        setError("");
        return true;
    };
    const { tab, viewer, navigate } = useCampaignNavigation(close),
        arbitrator = viewer === "arbitrator";
    const [dark, setDark] = useCampaignTheme();
    const phase = M.getPhase(state, state.currentPhase);
    async function commit(operation, success) {
        if (saving.current) return;
        saving.current = true;
        try {
            await update(operation);
            setMessage(success);
            close(true);
        } catch (error) {
            setError(error.message);
        } finally {
            saving.current = false;
        }
    }
    const visibleBattles = state.battles.filter(
        (b) => battleCycle === "all" || b.cycle === battleCycle,
    );
    return (
        <ErrorContext.Provider value={error}>
            <div className={`history-page cp-page ${dark ? "dark" : ""}`}>
                <CampaignNavigation
                    state={state}
                    dark={dark}
                    setDark={setDark}
                    navigate={navigate}
                />
                <CampaignFrame>
                    <div
                        className={
                            tab === "dashboard" ? "" : "max-w-3xl space-y-8"
                        }
                    >
                        {tab !== "dashboard" && (
                            <CampaignSubpageHeader
                                state={state}
                                tab={tab}
                                navigate={navigate}
                            />
                        )}
                        <div
                            className="cp-viewer-toggle"
                            aria-label="Demo viewing mode"
                        >
                            <span className="cp-help">Viewing as {viewer}</span>
                            <Button
                                variant="default"
                                onClick={() =>
                                    navigate(
                                        tab,
                                        arbitrator ? "player" : "arbitrator",
                                    )
                                }
                            >
                                Switch to {arbitrator ? "player" : "arbitrator"}{" "}
                                view
                            </Button>
                        </div>
                        {message && (
                            <div className="cp-message" role="status">
                                <Icon icon={CircleCheck} size={16} />
                                <span>{message}</span>
                                <Button
                                    icon={X}
                                    aria-label="Dismiss message"
                                    title="Dismiss message"
                                    onClick={() => setMessage("")}
                                />
                            </div>
                        )}
                        {(persistError || storageBlocked) && (
                            <p role="alert" className="cp-error">
                                {storageBlocked
                                    ? "Saved campaign data could not be read. The saved copy is preserved; changes stay in memory until you reset this demo."
                                    : "Browser storage is unavailable. Changes last until you close this page."}
                            </p>
                        )}
                        {tab === "dashboard" && (
                            <CampaignDashboard
                                state={state}
                                arbitrator={arbitrator}
                                navigate={navigate}
                                setModal={setModal}
                                reopen={() =>
                                    commit(
                                        M.reopenCampaign,
                                        "Campaign reopened.",
                                    )
                                }
                                onShare={async () => {
                                    try {
                                        await navigator.clipboard.writeText(
                                            new URL(
                                                "/campaign/",
                                                location.origin,
                                            ).href,
                                        );
                                        setMessage("Campaign link copied.");
                                    } catch {
                                        setMessage(
                                            "Copy the campaign address from your browser.",
                                        );
                                    }
                                }}
                                battles={
                                    <BattleList
                                        battles={state.battles.slice(0, 5)}
                                        state={state}
                                        onView={(battle) =>
                                            setModal({
                                                kind: "battle-detail",
                                                value: battle,
                                            })
                                        }
                                    />
                                }
                                rewardTable={<RewardTable phase={phase} />}
                            />
                        )}
                        {tab === "activity" && (
                            <Card title="Campaign log">
                                <div className="p-4">
                                    <CampaignActivity state={state} all />
                                </div>
                            </Card>
                        )}
                        {tab === "schedule" && (
                            <CampaignSchedule
                                state={state}
                                arbitrator={arbitrator}
                                change={commit}
                                openModal={setModal}
                            />
                        )}
                        {tab === "battles" && (
                            <>
                                <div className="cp-section-heading">
                                    <div>
                                        <h2>Battles</h2>
                                        <p>
                                            Each battle keeps its cycle, phase
                                            and rewards.
                                        </p>
                                    </div>
                                    {!state.ended && (
                                        <Button
                                            variant="primary"
                                            icon={Plus}
                                            onClick={() =>
                                                setModal({ kind: "battle" })
                                            }
                                        >
                                            Record a battle
                                        </Button>
                                    )}
                                </div>
                                <div className="cp-filter">
                                    <Select
                                        label="Filter by cycle"
                                        value={battleCycle}
                                        onChange={setBattleCycle}
                                        options={[
                                            ["all", "All cycles"],
                                            ...cycleOptions(state),
                                        ]}
                                    />
                                </div>
                                <Card
                                    title={`${visibleBattles.length} ${visibleBattles.length === 1 ? "battle" : "battles"}`}
                                    icon={Swords}
                                >
                                    <BattleList
                                        battles={visibleBattles}
                                        state={state}
                                        onView={(battle) =>
                                            setModal({
                                                kind: "battle-detail",
                                                value: battle,
                                            })
                                        }
                                    />
                                </Card>
                            </>
                        )}
                        <footer className="cp-demo-footer">
                            <p>
                                Campaign design demo · Changes are saved in this
                                browser.
                            </p>
                            <div>
                                <Button
                                    icon={RotateCcw}
                                    onClick={() => setModal({ kind: "reset" })}
                                >
                                    Reset demo
                                </Button>
                            </div>
                        </footer>
                    </div>
                </CampaignFrame>
                {error && !modal && (
                    <div className="cp-fixed-error" role="alert">
                        {error}
                        <Button
                            aria-label="Dismiss error"
                            icon={X}
                            onClick={() => setError("")}
                        />
                    </div>
                )}
                {modal?.kind === "roll" && (
                    <Modal title="Log a dice roll" onClose={close}>
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                const expression = new FormData(
                                    e.currentTarget,
                                ).get("dice");
                                commit((d) => {
                                    const result = M.roll(expression);
                                    M.note(
                                        d,
                                        `Rolled ${expression}: ${result.dice.join(", ")}. Result: ${result.value}.`,
                                    );
                                }, "Dice roll recorded.");
                            }}
                        >
                            <label className="history-field">
                                <span className={cotton.label}>Dice</span>
                                <select
                                    name="dice"
                                    className={cotton.select.className}
                                    style={cotton.select.style}
                                >
                                    <option value="d6">D6</option>
                                    <option value="2d6">2D6</option>
                                    <option value="d3">D3</option>
                                </select>
                            </label>
                            <FormFoot onClose={close} label="Roll and record" />
                        </form>
                    </Modal>
                )}
                {modal?.kind === "phase" && (
                    <PhaseForm
                        phase={modal.value}
                        state={state}
                        close={close}
                        save={(value) =>
                            commit((s) => M.savePhase(s, value), "Phase saved.")
                        }
                    />
                )}
                {modal?.kind === "cycle" && (
                    <CycleForm
                        cycle={modal.value}
                        state={state}
                        close={close}
                        save={(value) =>
                            commit((s) => M.saveCycle(s, value), "Cycle saved.")
                        }
                    />
                )}
                {modal?.kind === "settings" && (
                    <SettingsForm
                        closeGuard={closeGuard}
                        state={state}
                        close={close}
                        save={(value) =>
                            commit(
                                (s) => M.saveSettings(s, value),
                                "Schedule saved.",
                            )
                        }
                    />
                )}
                {modal?.kind === "battle" && (
                    <BattleForm
                        state={state}
                        close={close}
                        save={(value) =>
                            commit(
                                (s) => M.recordBattle(s, value),
                                "Battle recorded. Rewards added to the demo gangs.",
                            )
                        }
                    />
                )}
                {modal?.kind === "delete-cycle" && (
                    <Modal title={`Delete ${modal.value.name}`} onClose={close}>
                        <div className="cp-dialog-content">
                            <p>
                                Remove {modal.value.name} from the schedule?
                                Remaining cycles will be renumbered.
                            </p>
                            {modal.value.id === state.currentCycle && (
                                <p>
                                    The following cycle becomes current,
                                    together with its phase.
                                </p>
                            )}
                            <footer>
                                <Button variant="default" onClick={close}>
                                    Cancel
                                </Button>
                                <Button
                                    variant="default"
                                    onClick={() =>
                                        commit(
                                            (s) =>
                                                M.deleteCycle(
                                                    s,
                                                    modal.value.id,
                                                ),
                                            "Cycle deleted.",
                                        )
                                    }
                                >
                                    Delete cycle
                                </Button>
                            </footer>
                        </div>
                    </Modal>
                )}
                {modal?.kind === "end-cycle" && (
                    <EndCycleForm
                        state={state}
                        close={close}
                        save={(value) =>
                            commit((s) => {
                                if (s.currentCycle !== value.currentCycle)
                                    throw new Error(
                                        "The current cycle changed. Close this dialog and review it before ending another cycle.",
                                    );
                                M.endCycle(s, value);
                            }, "Cycle ended. The campaign period has been updated.")
                        }
                    />
                )}
                {modal?.kind === "battle-detail" && (
                    <Modal title={modal.value.name} onClose={close}>
                        <div className="cp-dialog-content">
                            <div className="cp-inline">
                                <Tag>{modal.value.cycleName}</Tag>
                                <Tag>{modal.value.phaseName}</Tag>
                            </div>
                            <p>
                                {modal.value.participants
                                    .map((g) => gangName(state, g))
                                    .join(" vs ")}
                                <br />
                                <strong>
                                    {modal.value.winner === "draw"
                                        ? "Draw"
                                        : `${gangName(state, modal.value.winner)} won`}
                                </strong>
                            </p>
                            <h3>Recorded rewards</h3>
                            {modal.value.payouts.map((p) => (
                                <div className="cp-payout" key={p.gang}>
                                    <span>
                                        {gangName(state, p.gang)}
                                        <small>Dice: {p.rolls}</small>
                                    </span>
                                    <strong>
                                        +{p.credits}¢ ·{" "}
                                        {p.reputation > 0 ? "+" : ""}
                                        {p.reputation} rep
                                    </strong>
                                </div>
                            ))}
                            <p className="cp-help">
                                These rewards and period labels are kept with
                                the battle. Later schedule edits do not
                                recalculate them.
                            </p>
                            <footer>
                                <Button variant="default" onClick={close}>
                                    Close
                                </Button>
                            </footer>
                        </div>
                    </Modal>
                )}
                {modal?.kind === "reset" && (
                    <Modal title="Reset this demo" onClose={close}>
                        <div className="cp-dialog-content">
                            <p>
                                Replace changes in this campaign demo with the
                                seven-cycle example. This only resets the
                                campaign demo in this browser.
                            </p>
                            <footer>
                                <Button variant="default" onClick={close}>
                                    Cancel
                                </Button>
                                <Button
                                    variant="success"
                                    onClick={async () => {
                                        await reset();
                                        setMessage("Campaign demo reset.");
                                        setBattleCycle("all");
                                        close();
                                    }}
                                >
                                    Reset demo
                                </Button>
                            </footer>
                        </div>
                    </Modal>
                )}
            </div>
        </ErrorContext.Provider>
    );
}
const host = document.querySelector("#campaign-root"),
    shadow = host.attachShadow({ mode: "open" }),
    style = document.createElement("link");
style.rel = "stylesheet";
style.href = host.dataset.themeUrl;
shadow.append(style);
const root = document.createElement("div");
shadow.append(root);
createRoot(root).render(<App />);
