import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { Layout } from "../components/Layout";
import { Alert } from "../components/Alert";
import styles from "./Verify.module.css";

type State = "working" | "missing" | "unusable" | "offline";

export function Verify() {
  const navigate = useNavigate();
  const [state, setState] = useState<State>("working");
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const token = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token");
    // Clear the token from the address bar before doing anything with it.
    window.history.replaceState(null, "", window.location.pathname);

    if (!token) {
      setState("missing");
      return;
    }

    api
      .verify(token)
      .then(() => navigate("/ask", { replace: true }))
      .catch((caught: unknown) => {
        if (caught instanceof ApiError && caught.kind === "network") {
          setState("offline");
        } else if (caught instanceof ApiError && caught.kind === "unavailable") {
          setState("offline");
        } else {
          setState("unusable");
        }
      });
  }, [navigate]);

  return (
    <Layout>
      <h1>Signing you in</h1>
      {state === "working" ? (
        <p role="status">Checking your link…</p>
      ) : null}

      {state === "missing" ? (
        <div className={styles.panel}>
          <Alert tone="error">This link is missing its token.</Alert>
          <p>
            Open the link from your email again, or <Link to="/sign-in">request a new one</Link>.
          </p>
        </div>
      ) : null}

      {state === "unusable" ? (
        <div className={styles.panel}>
          <Alert tone="error">
            This link cannot be used. It may have expired, or it may already have been used.
          </Alert>
          <p>
            <Link to="/sign-in">Request a new sign-in link</Link>.
          </p>
        </div>
      ) : null}

      {state === "offline" ? (
        <div className={styles.panel}>
          <Alert tone="error">We could not reach Firebrief. Check your connection and try again.</Alert>
          <p>
            <Link to="/sign-in">Start again</Link>.
          </p>
        </div>
      ) : null}
    </Layout>
  );
}
