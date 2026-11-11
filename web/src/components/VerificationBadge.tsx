import styles from "./VerificationBadge.module.css";

export function VerificationBadge({ quotes }: { quotes: number }) {
  const label = quotes === 1 ? "Verified against 1 quote" : `Verified against ${quotes} quotes`;
  return (
    <p className={styles.badge}>
      <span className={styles.mark} aria-hidden="true">
        ✓
      </span>
      {label}
    </p>
  );
}
