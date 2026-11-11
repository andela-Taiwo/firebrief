import { Link, useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import { SkipLink } from "./SkipLink";
import { Button } from "./Button";
import styles from "./Layout.module.css";

export function Layout({ children, signedIn }: { children: ReactNode; signedIn?: boolean }) {
  const navigate = useNavigate();
  const location = useLocation();

  async function signOut() {
    try {
      await api.logout();
    } finally {
      navigate("/signed-out", { replace: true });
    }
  }

  return (
    <div className={styles.shell}>
      <SkipLink />
      <header className={styles.header}>
        <Link className={styles.brand} to="/">
          Firebrief
        </Link>
        <nav aria-label="Account">
          {location.pathname.startsWith("/sign-in") ? null : signedIn ? (
            <Button variant="quiet" onClick={signOut}>
              Sign out
            </Button>
          ) : (
            <Link to={`/sign-in?next=${encodeURIComponent(location.pathname)}`}>Sign in</Link>
          )}
        </nav>
      </header>
      <main id="main" className={styles.main}>
        {children}
      </main>
      <footer className={styles.footer}>
        <p>
          Firebrief quotes UK government guidance. It is not professional advice.
        </p>
        <ul className={styles.footerLinks}>
          <li>
            <Link to="/about">How verification works</Link>
          </li>
          <li>
            <Link to="/help">Help</Link>
          </li>
          <li>
            <Link to="/accessibility">Accessibility</Link>
          </li>
        </ul>
      </footer>
    </div>
  );
}
