import {
    Breadcrumbs,
    Alert,
    GangFigures,
    UserLink,
    WorkflowPage,
} from "../../ui";
import type { HireProps } from "./types";
import { Catalogue } from "./Catalogue";
import { Confirmation } from "./Confirmation";
import { useState } from "react";

export function Hire(props: HireProps) {
    const [figures, setFigures] = useState(props.figures);
    return (
        <>
            <WorkflowPage
                title="Hire fighters"
                lead="Choose a profile and its options, then confirm the name, payment and rating."
                breadcrumb={
                    <Breadcrumbs
                        items={[
                            { label: <UserLink {...props.owner} /> },
                            { label: props.gangName, href: props.gangHref },
                            { label: "Hire fighters" },
                        ]}
                    />
                }
                footer={null}
                onSubmit={(event) => event.preventDefault()}
            >
                <GangFigures data={figures} />
                {props.notice && <Alert tone="warning">{props.notice}</Alert>}
                {props.messages.map((message, index) => (
                    <Alert key={index} tone={message.tone}>
                        {message.text}
                    </Alert>
                ))}
                <Catalogue {...props} />
            </WorkflowPage>
            <Confirmation {...props} onFigures={setFigures} />
        </>
    );
}
