import type { Redaction } from "../lib/api";
import styles from "./RedactionNotice.module.css";

const LABELS: Record<string, [string, string]> = {
  email: ["email address", "email addresses"],
  phone: ["phone number", "phone numbers"],
  postcode: ["postcode", "postcodes"],
  national_insurance: ["national insurance number", "national insurance numbers"],
  card: ["card number", "card numbers"],
};

export function RedactionNotice({ redactions }: { redactions: Redaction[] }) {
  if (redactions.length === 0) return null;
  const parts = redactions.map(({ kind, count }) => {
    const [one, many] = LABELS[kind] ?? [kind, kind];
    return `${count} ${count === 1 ? one : many}`;
  });

  return (
    <p className={styles.notice}>
      We removed {parts.join(" and ")} before searching, so they were never sent to the model.
    </p>
  );
}
