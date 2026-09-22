# Generate the fixed SVG layouts. Keep the companion Mermaid diagrams in sync.
from html import escape
from pathlib import Path

out = Path(__file__).resolve().parent


def svg(width, height, title, desc, nodes, edges):
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc"><title id="title">{escape(title)}</title><desc id="desc">{escape(desc)}</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#697386"/></marker></defs><style>text{{font-family:system-ui,sans-serif;fill:#202a3c}}.head{{font-size:16px;font-weight:650}}.detail{{font-size:13px;fill:#697386}}.label{{font-size:12px;fill:#46556a;paint-order:stroke;stroke:#f7f8fa;stroke-width:6;stroke-linejoin:round}}</style>'
    ]
    for path, x, y, label in edges:
        parts.append(
            f'<path d="{path}" fill="none" stroke="#697386" stroke-width="1.6" marker-end="url(#arrow)"/>'
        )
        if label:
            parts.append(
                f'<text class="label" x="{x}" y="{y}" text-anchor="middle">{escape(label)}</text>'
            )
    for x, y, w, h, head, lines in nodes:
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="white" stroke="#cbd2dc"/><text class="head" x="{x + 16}" y="{y + 28}">{escape(head)}</text>'
        )
        for j, line in enumerate(lines):
            parts.append(
                f'<text class="detail" x="{x + 16}" y="{y + 53 + j * 19}">{escape(line)}</text>'
            )
    parts.append("</svg>")
    return "".join(parts) + "\n"


nodes = [
    (
        20,
        30,
        290,
        100,
        "Effective action access",
        ["Existing Assignment or computed grant", "NEW assignable Action kind"],
    ),
    (
        395,
        30,
        295,
        100,
        "Action",
        ["What may be performed", "Owns use_price and outcome choices"],
    ),
    (
        780,
        30,
        295,
        100,
        "Price components",
        ["All components are required", "[] means no payment"],
    ),
    (
        20,
        220,
        290,
        100,
        "Rank table + XP change",
        ["Current assigned table", "Counter values before and after"],
    ),
    (
        395,
        220,
        295,
        100,
        "Allowance rule",
        ["Part of the action definition", "Recruitment grant or rank award"],
    ),
    (
        780,
        220,
        295,
        100,
        "Outcome",
        ["Augment / resolve slot / apply changes", "One is selected per action record"],
    ),
    (
        395,
        420,
        295,
        110,
        "Allowance",
        [
            "One earned or granted use",
            "Source recorded once",
            "May be unused, reserved or used",
        ],
    ),
    (
        780,
        420,
        295,
        110,
        "Action record",
        [
            "One use: started or completed",
            "References action and selected outcome",
            "Payment only on completion",
        ],
    ),
    (
        395,
        650,
        295,
        110,
        "Changes",
        [
            "Ledger events linked to the use",
            "Picks, tiers and counters changed",
            "Stored together with completion",
        ],
    ),
    (
        780,
        650,
        295,
        110,
        "Payment and lines",
        [
            "Optional group of ledger events",
            "Paid with the completed result",
            "Remembers the original balances",
        ],
    ),
]
edges = [
    ("M310 80H395", 352, 64, "refers to"),
    ("M690 80H780", 735, 64, "use_price"),
    ("M542 130V220", 590, 178, "0..1 rule"),
    ("M690 110L755 170H928V220", 794, 158, "1..many outcomes"),
    ("M310 270H395", 352, 248, "rank input"),
    ("M542 320V420", 592, 370, "awards once"),
    ("M690 475H780", 735, 449, "0..1 current use"),
    ("M928 320V420", 974, 370, "selected"),
    ("M928 530V650", 984, 590, "0..1 payment"),
    ("M830 530L635 650", 708, 600, "0..many changes"),
]
(out / "action-relationships.svg").write_text(
    svg(
        1100,
        800,
        "Action relationships",
        "Actions own price components, allowance rules and outcomes. Rules award allowances, which can fund action records. Records link to payments and changes. The current rank table and XP change supply grant inputs.",
        nodes,
        edges,
    )
)
nodes = [
    (
        325,
        25,
        460,
        95,
        "Recruitment or XP increase",
        [
            "Run within the player’s save operation",
            "Read effective action access and the current table",
        ],
    ),
    (
        325,
        175,
        460,
        100,
        "Apply the allowance rule",
        [
            "For ranks: before XP < threshold ≤ after XP",
            "Create each crossed threshold once; retain earlier grants",
        ],
    ),
    (
        325,
        335,
        460,
        90,
        "Read this allowance’s state",
        ["Unused, started, or completed"],
    ),
    (
        20,
        490,
        330,
        115,
        "Unused allowance",
        [
            "Player starts the action",
            "Reserve allowance + create record",
            "Together, under the gang lock",
        ],
    ),
    (
        385,
        490,
        330,
        115,
        "Started allowance",
        [
            "Continue its existing action record",
            "Keep all recorded rolls and choices",
            "Do not create another use",
        ],
    ),
    (
        750,
        490,
        330,
        115,
        "Completed allowance",
        ["Show its existing result and history", "No new use of this allowance"],
    ),
    (
        210,
        705,
        510,
        100,
        "Action record: started",
        [
            "Make required selections or rolls",
            "Leaving returns to this same record later",
        ],
    ),
    (
        210,
        895,
        510,
        110,
        "Complete together",
        [
            "Write the outcome’s changes and mark the record complete",
            "The allowance now points to a completed use",
            "Corrections append history to that same use",
        ],
    ),
]
edges = [
    ("M555 120V175", 638, 152, "assess grant"),
    ("M555 275V335", 648, 308, "source uniqueness"),
    ("M455 425L185 490", 270, 453, "unused"),
    ("M555 425V490", 605, 460, "started"),
    ("M665 425L915 490", 810, 453, "completed"),
    ("M185 605V660H465V705", 260, 650, "new record"),
    ("M550 605V705", 625, 660, "existing record"),
    ("M465 805V895", 570, 856, "selections finished"),
]
(out / "action-allowance-flow.svg").write_text(
    svg(
        1100,
        1040,
        "Allowance rule to completed action",
        "A player-triggered operation awards each source once. An unused allowance starts one record; a started allowance continues its existing record; a completed allowance cannot start again.",
        nodes,
        edges,
    )
)
nodes = [
    (
        325,
        25,
        500,
        120,
        "Choose the result",
        [
            "Select the outcome, item and tier as needed",
            "Save an unpaid ActionRecord to continue later",
            "Clearing glitches skips item selection",
        ],
    ),
    (
        910,
        25,
        280,
        120,
        "Cancel unfinished action",
        ["Cancel the saved choices", "No payment to refund"],
    ),
    (
        325,
        225,
        500,
        115,
        "Review and pay",
        [
            "Review the selected result and every price component",
            "Final confirmation is the payment point",
        ],
    ),
    (
        325,
        415,
        500,
        115,
        "Validate under the gang lock",
        [
            "Check record revision, review, balances and exact targets",
            "A completed record returns its existing receipt",
        ],
    ),
    (
        20,
        630,
        330,
        115,
        "Already completed",
        ["Return the same record and receipt", "Do not charge again"],
    ),
    (
        405,
        630,
        370,
        140,
        "Valid confirmation",
        [
            "One transaction: every payment debit",
            "+ result changes + completed state",
            "Tier changes and glitch clearing",
            "use this same boundary",
        ],
    ),
    (
        830,
        630,
        370,
        140,
        "Changed or insufficient",
        [
            "Keep the record unfinished",
            "Refresh the review or item selections",
            "No payment or result change",
        ],
    ),
    (
        405,
        875,
        370,
        115,
        "Failure before commit",
        [
            "Roll back every debit and result change",
            "Leave the saved choices unfinished",
        ],
    ),
]
edges = [
    ("M825 85H910", 865, 68, "cancel"),
    ("M575 145V225", 638, 190, "choices ready"),
    ("M575 340V415", 680, 382, "confirm purchase"),
    ("M420 530L185 630", 230, 577, "repeat request"),
    ("M575 530L590 630", 644, 584, "valid"),
    ("M735 530L1015 630", 940, 580, "needs review"),
    ("M1200 680H1220V282H825", 1090, 267, "review again"),
    ("M590 770V875", 683, 832, "transaction fails"),
]
(out / "action-payment-flow.svg").write_text(
    svg(
        1240,
        1030,
        "Final checkout for paid actions",
        "All choices are unpaid until final confirmation. Cancellation needs no refund. Confirmation validates the review and atomically commits payment, result changes and completion. Repeats return the existing receipt; changed terms return to review; failures roll back.",
        nodes,
        edges,
    )
)
print("Wrote relationships, allowance lifecycle and final checkout diagrams.")
