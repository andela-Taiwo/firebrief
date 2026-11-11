import type { ReactNode } from "react";
import styles from "./Alert.module.css";

type Tone = "info" | "warning" | "error";

export function Alert({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div
      className={`${styles.alert} ${styles[tone]}`}
      role={tone === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}
