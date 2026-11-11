import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { AnswerResponse } from "../lib/api";
import { retryTime } from "../lib/format";
import { Layout } from "../components/Layout";
import { Field } from "../components/Field";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import { AnswerProgress } from "../components/AnswerProgress";
import { AnswerCard } from "../components/AnswerCard";
import { SourceList } from "../components/SourceList";
import { RefusalPanel } from "../components/RefusalPanel";
import { RedactionNotice } from "../components/RedactionNotice";
import styles from "./Ask.module.css";

const EXAMPLES = [
  "How long can a dead end be in a block of flats?",
  "Do flat entrance doors need to be self-closing?",
];

type Status =
  | { kind: "idle" }
  | { kind: "asking"; startedAt: number }
  | { kind: "answered"; result: AnswerResponse }
  | { kind: "failed"; message: string; retryAt?: string };

export function Ask() {
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [signedIn, setSignedIn] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const panelRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLHeadingElement>(null);
  const asking = status.kind === "asking";

  useEffect(() => {
    api
      .me()
      .then(() => setSignedIn(true))
      .catch((caught: unknown) => {
        if (caught instanceof ApiError && caught.kind === "unauthorised") {
          navigate("/sign-in?next=/ask", { replace: true });
        }
      });
  }, [navigate]);

  useEffect(() => {
    if (status.kind === "answered") {
      if (status.result.answer) headingRef.current?.focus();
      else panelRef.current?.focus();
    }
    if (status.kind === "failed") errorRef.current?.focus();
  }, [status]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const value = question.trim();
    if (value.length < 2) return;
    setStatus({ kind: "asking", startedAt: Date.now() });
    try {
      const result = await api.ask(value);
      setStatus({ kind: "answered", result });
    } catch (caught) {
      if (caught instanceof ApiError) {
        if (caught.kind === "unauthorised") {
          navigate("/sign-in?next=/ask", { replace: true });
          return;
        }
        if (caught.kind === "too_many" && caught.retryAfterSeconds) {
          setStatus({
            kind: "failed",
            message: "Too many questions. Try again at " + retryTime(caught.retryAfterSeconds) + ".",
            retryAt: retryTime(caught.retryAfterSeconds),
          });
          return;
        }
        if (caught.kind === "unavailable") {
          setStatus({
            kind: "failed",
            message: "Firebrief is temporarily unavailable. Nothing was charged. Try again in a moment.",
          });
          return;
        }
        if (caught.kind === "network") {
          setStatus({
            kind: "failed",
            message: "We could not reach Firebrief. Check your connection and try again.",
          });
          return;
        }
        if (caught.kind === "invalid") {
          setStatus({
            kind: "failed",
            message: "That request could not be completed. Check the question and try again.",
          });
          return;
        }
      }
      setStatus({ kind: "failed", message: "Something went wrong. Try again." });
    }
  }

  const result = status.kind === "answered" ? status.result : null;

  return (
    <Layout signedIn={signedIn}>
      <h1>Ask about fire safety guidance</h1>
      <p className={styles.intro}>
        Answers quote the guidance and link to it. If the guidance does not answer the question, we
        say so.
      </p>

      <form className={styles.form} onSubmit={submit}>
        <Field
          label="Your question"
          multiline
          name="question"
          maxLength={2000}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          hint={`${question.length} of 2000 characters.`}
          disabled={asking}
        />
        <div className={styles.actions}>
          <Button type="submit" disabled={asking || question.trim().length < 2}>
            {asking ? "Asking…" : "Ask"}
          </Button>
          {status.kind === "idle"
            ? EXAMPLES.map((example) => (
                <Button
                  key={example}
                  type="button"
                  variant="quiet"
                  onClick={() => setQuestion(example)}
                >
                  {example}
                </Button>
              ))
            : null}
        </div>
      </form>

      {asking ? <AnswerProgress startedAt={status.startedAt} /> : null}

      {status.kind === "failed" ? (
        <div className={styles.error} role="alert">
          <h2 ref={errorRef} tabIndex={-1}>
            That did not work
          </h2>
          <p>{status.message}</p>
          <Button onClick={() => setStatus({ kind: "idle" })}>Try again</Button>
        </div>
      ) : null}

      {result ? (
        <div className={styles.result}>
          <p className="visually-hidden" role="status">
            {result.answer ? "Answer ready." : "We could not answer that."}
          </p>
          {result.redactions.length > 0 ? <RedactionNotice redactions={result.redactions} /> : null}
          {result.answer ? (
            <>
              <AnswerCard ref={headingRef} answer={result.answer} sources={result.sources} />
              <SourceList sources={result.sources} />
            </>
          ) : result.refusal ? (
            <>
              <RefusalPanel ref={panelRef} refusal={result.refusal} sources={result.sources.length} />
              <SourceList sources={result.sources} />
            </>
          ) : null}
          <p className={styles.secondary}>
            <Link to="/help">What the refusals mean</Link>
          </p>
        </div>
      ) : null}
    </Layout>
  );
}
