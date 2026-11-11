import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { retryTime } from "../lib/format";
import { Layout } from "../components/Layout";
import { Field } from "../components/Field";
import { Button } from "../components/Button";
import { Alert } from "../components/Alert";
import styles from "./SignIn.module.css";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function SignIn() {
  const [params] = useSearchParams();
  const invited = params.get("tenant") ?? "";
  const next = params.get("next") ?? "/ask";
  const [email, setEmail] = useState("");
  const [tenant, setTenant] = useState(invited);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [blockedUntil, setBlockedUntil] = useState<Date | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!blockedUntil) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [blockedUntil]);

  const blocked = blockedUntil !== null && blockedUntil.getTime() > now;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setValidationError(null);
    setRequestError(null);
    if (!UUID.test(tenant)) {
      setValidationError("The workspace ID should look like 8-4-4-4-12 hexadecimal characters.");
      return;
    }
    setSending(true);
    try {
      await api.requestMagicLink(tenant, email);
      setSent(true);
    } catch (caught) {
      if (caught instanceof ApiError && caught.kind === "too_many" && caught.retryAfterSeconds) {
        setBlockedUntil(new Date(Date.now() + caught.retryAfterSeconds * 1000));
        setRequestError(`Too many attempts. Try again at ${retryTime(caught.retryAfterSeconds)}.`);
      } else if (caught instanceof ApiError && caught.kind === "network") {
        setRequestError("We could not reach Firebrief. Check your connection and try again.");
      } else if (caught instanceof ApiError && caught.kind === "unavailable") {
        setRequestError("Firebrief is temporarily unavailable. Try again in a moment.");
      } else {
        setRequestError("We could not send the link. Try again.");
      }
    } finally {
      setSending(false);
    }
  }

  return (
    <Layout>
      <h1>Sign in</h1>
      <p className={styles.intro}>
        We will email you a link that signs you in. There is no password to remember.
      </p>

      {sent ? (
        <div className={styles.sent}>
          <h2>Check your email</h2>
          <p>
            If <strong>{email}</strong> belongs to this workspace, a sign-in link is on its way. It
            expires in 15 minutes and works once.
          </p>
          <p>
            <Button variant="secondary" onClick={() => setSent(false)} disabled={blocked}>
              Send another link
            </Button>
          </p>
          {blocked && blockedUntil ? (
            <p className={styles.hint}>
              You can request another link at{" "}
              {blockedUntil.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}.
            </p>
          ) : null}
        </div>
      ) : (
        <form className={styles.form} onSubmit={submit} noValidate>
          <Field
            label="Email address"
            type="email"
            name="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            hint="Use the address your organisation invited."
          />
          {invited ? (
            <input type="hidden" name="tenant" value={tenant} />
          ) : (
            <Field
              label="Workspace ID"
              name="tenant"
              required
              value={tenant}
              onChange={(event) => setTenant(event.target.value)}
              hint="Your administrator gives you this. It is in your invitation link."
              error={validationError ?? undefined}
            />
          )}
          {requestError ? <Alert tone="error">{requestError}</Alert> : null}
          <Button type="submit" disabled={sending || blocked || email.length < 3}>
            {sending ? "Sending…" : "Email me a sign-in link"}
          </Button>
          <p className={styles.hint}>
            Trouble signing in? <Link to="/help">Read the help page</Link>.
          </p>
          <input type="hidden" name="next" value={next} />
        </form>
      )}
    </Layout>
  );
}
