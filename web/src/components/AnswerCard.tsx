import { forwardRef } from "react";
import type { Source } from "../lib/api";
import { VerificationBadge } from "./VerificationBadge";
import styles from "./AnswerCard.module.css";

function withMarkerLinks(answer: string, sources: Source[]) {
  const parts = answer.split(/(\[\d+\])/g);
  return parts.map((part, index) => {
    const match = /^\[(\d+)\]$/.exec(part);
    if (!match) return <span key={index}>{part}</span>;
    const marker = Number(match[1]);
    const source = sources.find((item) => item.n === marker);
    return (
      <a
        key={index}
        href={`#source-${marker}`}
        className={styles.marker}
        aria-label={
          source
            ? `Source ${marker}: ${source.title}, edition ${source.edition}`
            : `Source ${marker}`
        }
      >
        [{marker}]
      </a>
    );
  });
}

export const AnswerCard = forwardRef<HTMLHeadingElement, { answer: string; sources: Source[] }>(
  function AnswerCard({ answer, sources }, ref) {
    const quotes = sources.reduce((total, source) => total + source.quotes.length, 0);

    return (
      <section className={styles.card} aria-labelledby="answer-heading">
        <h2 id="answer-heading" ref={ref} tabIndex={-1}>
          Answer
        </h2>
        <VerificationBadge quotes={quotes} />
        <p className={styles.answer}>{withMarkerLinks(answer, sources)}</p>
      </section>
    );
  },
);
