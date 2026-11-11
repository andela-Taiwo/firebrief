import { useId } from "react";
import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";
import styles from "./Field.module.css";

interface Base {
  label: string;
  hint?: string;
  error?: string;
}

type InputProps = Base & InputHTMLAttributes<HTMLInputElement> & { multiline?: false };
type AreaProps = Base & TextareaHTMLAttributes<HTMLTextAreaElement> & { multiline: true };

export function Field(props: InputProps | AreaProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [props.hint ? hintId : null, props.error ? errorId : null].filter(Boolean).join(" ");
  const { label, hint, error, multiline, ...rest } = props;

  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>
        {label}
      </label>
      {hint ? (
        <p className={styles.hint} id={hintId}>
          {hint}
        </p>
      ) : null}
      {error ? (
        <p className={styles.error} id={errorId}>
          {error}
        </p>
      ) : null}
      {multiline ? (
        <textarea
          id={id}
          className={styles.control}
          aria-describedby={describedBy || undefined}
          aria-invalid={error ? true : undefined}
          {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)}
        />
      ) : (
        <input
          id={id}
          className={styles.control}
          aria-describedby={describedBy || undefined}
          aria-invalid={error ? true : undefined}
          {...(rest as InputHTMLAttributes<HTMLInputElement>)}
        />
      )}
    </div>
  );
}
