import { useEffect, useState } from "react";
import styles from "./AnswerProgress.module.css";

/** One honest status. The elapsed timer is decorative and kept out of the live region. */
export function AnswerProgress({ startedAt }: { startedAt: number }) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  return (
    <div className={styles.progress}>
      <p className={styles.status} role="status">
        {seconds < 3 ? "Searching the guidance…" : "Still working — this takes a few seconds."}
      </p>
      <p className={styles.timer} aria-hidden="true">
        {seconds}s
      </p>
    </div>
  );
}
