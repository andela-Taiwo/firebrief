import { forwardRef } from "react";
import type { Refusal } from "../lib/api";
import { REFUSAL_COPY } from "../screens/answerParts";
import styles from "./RefusalPanel.module.css";

export const RefusalPanel = forwardRef<HTMLHeadingElement, { refusal: Refusal; sources: number }>(
  function RefusalPanel({ refusal, sources }, ref) {
    const copy = REFUSAL_COPY[refusal.reason] ?? {
      title: "We could not answer that",
      body: refusal.message,
      next: "Try rephrasing the question.",
    };

    return (
      <section className={styles.panel} aria-labelledby="refusal-heading">
        <h2 id="refusal-heading" ref={ref} tabIndex={-1}>
          {copy.title}
        </h2>
        <p>{copy.body}</p>
        <p className={styles.next}>{copy.next}</p>
        {refusal.details.length > 0 ? (
          <details className={styles.details}>
            <summary>Why this was withheld</summary>
            <ul>
              {refusal.details.map((detail) => (
                <li key={detail}>{detail}</li>
              ))}
            </ul>
          </details>
        ) : null}
        {sources > 0 ? (
          <p className={styles.evidence}>
            {sources === 1 ? "1 source was considered" : `${sources} sources were considered`}. They are
            listed below.
          </p>
        ) : null}
      </section>
    );
  },
);
