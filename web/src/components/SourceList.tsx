import type { Source } from "../lib/api";
import { sourceHref } from "../lib/format";
import { VisuallyHidden } from "./VisuallyHidden";
import styles from "./SourceList.module.css";

export function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;

  return (
    <section aria-labelledby="sources-heading" className={styles.section}>
      <h2 id="sources-heading">Sources</h2>
      <ol className={styles.list}>
        {sources.map((source) => {
          const passage = source.quotes[0]?.text;
          return (
            <li key={source.n} id={`source-${source.n}`} className={styles.item}>
              <h3 className={styles.title}>
                <span className={styles.number} aria-hidden="true">
                  [{source.n}]
                </span>{" "}
                {source.title}
              </h3>
              <p className={styles.meta}>
                {source.heading} · Edition {source.edition}
                {source.cited ? "" : " · Considered, not quoted"}
                <VisuallyHidden>. {source.cited ? "Quoted in the answer" : "Not quoted in the answer"}</VisuallyHidden>
              </p>
              {source.quotes.map((quote) => (
                <blockquote key={`${source.n}-${quote.marker}-${quote.start}`} className={styles.quote}>
                  <p>“{quote.text}”</p>
                  <footer>
                    <a href={sourceHref(source.url, quote.text)} target="_blank" rel="noreferrer">
                      Open the guidance at this passage
                      <VisuallyHidden> (opens in a new tab)</VisuallyHidden>
                    </a>
                  </footer>
                </blockquote>
              ))}
              {source.quotes.length === 0 ? (
                <p>
                  <a href={sourceHref(source.url, passage)} target="_blank" rel="noreferrer">
                    Open the guidance
                    <VisuallyHidden> (opens in a new tab)</VisuallyHidden>
                  </a>
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
