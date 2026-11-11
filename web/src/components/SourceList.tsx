import type { Source } from "../lib/api";
import { sourceHref } from "../lib/format";
import { VisuallyHidden } from "./VisuallyHidden";
import styles from "./SourceList.module.css";

function leaf(heading: string): string {
  return heading.split(" > ").pop() ?? heading;
}

export function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null;
  const cited = sources.filter((source) => source.cited);
  const considered = sources.filter((source) => !source.cited);

  return (
    <section aria-labelledby="sources-heading" className={styles.section}>
      <h2 id="sources-heading">
        {cited.length > 0 ? "Quoted in this answer" : "Sources"}
      </h2>
      <ol className={styles.list}>
        {cited.map((source) => {
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
                {leaf(source.heading)} · Edition {source.edition}
                <VisuallyHidden>. This source is quoted in the answer.</VisuallyHidden>
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

      {considered.length > 0 ? (
        <details className={styles.more}>
          <summary>
            Also considered ({considered.length})
            <VisuallyHidden>. Sources we read but did not quote.</VisuallyHidden>
          </summary>
          <ul className={styles.list}>
            {considered.map((source) => (
              <li key={source.n} id={`source-${source.n}`} className={styles.item}>
                <p className={styles.title}>
                  <span className={styles.number} aria-hidden="true">
                    [{source.n}]
                  </span>{" "}
                  {source.title}
                </p>
                <p className={styles.meta}>
                  {leaf(source.heading)} · Edition {source.edition}
                </p>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
