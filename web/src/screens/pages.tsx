import { Link } from "react-router-dom";
import { Layout } from "../components/Layout";
import { SourceList } from "../components/SourceList";
import { AnswerCard } from "../components/AnswerCard";
import styles from "./Pages.module.css";

const EXAMPLE = {
  answer:
    "Dead ends must be limited in length to thirty metres. [1]",
  sources: [
    {
      n: 1,
      title: "Fire safety in flats",
      heading: "Escape routes",
      edition: "2019",
      url: "https://www.gov.uk/government/publications/fire-safety-in-purpose-built-flats",
      cited: true,
      quotes: [
        {
          marker: 1,
          text: "Dead ends must be limited in length to thirty metres.",
          start: 0,
          end: 55,
        },
      ],
    },
  ],
};

export function Landing() {
  return (
    <Layout>
      <h1>Answers about fire safety, with the guidance to back them up</h1>
      <p className={styles.lead}>
        Ask a question about UK fire safety guidance. Firebrief answers with quotes from the source,
        or explains why it cannot — and never guesses.
      </p>
      <p>
        <Link className={styles.cta} to="/sign-in">
          Sign in to ask a question
        </Link>
      </p>

      <section className={styles.example} aria-labelledby="example-heading">
        <h2 id="example-heading">What an answer looks like</h2>
        <p className={styles.capture}>
          Example answer · Fire safety in flats, edition 2019 · captured 11 November 2026 from the
          demonstration corpus. Figures and wording come from the source, not from us.
        </p>
        <AnswerCard answer={EXAMPLE.answer} sources={EXAMPLE.sources} />
        <SourceList sources={EXAMPLE.sources} />
      </section>

      <section aria-labelledby="trust-heading" className={styles.section}>
        <h2 id="trust-heading">Why you can check it</h2>
        <ul className={styles.list}>
          <li>Every claim carries a numbered quote from the guidance.</li>
          <li>You can open the document at the passage and read it yourself.</li>
          <li>If a quote cannot be matched to the source, the answer is withheld.</li>
        </ul>
      </section>

      <p>
        <Link to="/about">How verification works</Link>
      </p>
    </Layout>
  );
}

export function About() {
  return (
    <Layout>
      <h1>How Firebrief works</h1>
      <p className={styles.lead}>
        Firebrief is for fire safety managers, building owners and contractors who need an answer
        they can check, not a paragraph they have to trust.
      </p>

      <section aria-labelledby="steps" className={styles.section}>
        <h2 id="steps">What happens to your question</h2>
        <ol className={styles.list}>
          <li>Personal details are removed before anything leaves our servers.</li>
          <li>We search the guidance we hold and take the most relevant passages.</li>
          <li>A model drafts an answer that must quote those passages, with markers.</li>
          <li>Every quote is matched back to the exact text, and a second model checks support.</li>
          <li>If any quote fails, the answer is withheld and you are told why.</li>
        </ol>
      </section>

      <section aria-labelledby="limits" className={styles.section}>
        <h2 id="limits">What it will not do</h2>
        <ul className={styles.list}>
          <li>It does not answer from memory. If the guidance is silent, it refuses.</li>
          <li>It is not a substitute for professional advice or a fire risk assessment.</li>
          <li>It covers the documents listed in the product, not all UK guidance.</li>
        </ul>
      </section>
    </Layout>
  );
}

export function Help() {
  return (
    <Layout>
      <h1>Help</h1>

      <section aria-labelledby="asking" className={styles.section}>
        <h2 id="asking">Asking a good question</h2>
        <ul className={styles.list}>
          <li>Name the thing you are asking about: a door, a dead end, a detection system.</li>
          <li>One requirement at a time gives a sharper answer.</li>
          <li>Include the building type if the guidance differs by building.</li>
        </ul>
      </section>

      <section aria-labelledby="refusals" className={styles.section}>
        <h2 id="refusals">Why an answer might be withheld</h2>
        <dl className={styles.definitions}>
          <dt>The guidance does not cover it</dt>
          <dd>Nothing in the documents we hold answers the question. Try naming the regulation.</dd>
          <dt>The sources do not settle it</dt>
          <dd>We found relevant guidance, but it does not answer what you asked.</dd>
          <dt>We could not verify every quote</dt>
          <dd>One quote did not match the source, so the whole answer is withheld.</dd>
          <dt>The answer was cut off</dt>
          <dd>The answer stopped before it could be checked. Try a narrower question.</dd>
          <dt>Your usage limit is reached</dt>
          <dd>The question would exceed your organisation's limit. It resets on a fixed cycle.</dd>
          <dt>This question was already sent</dt>
          <dd>A request with the same identifier was already answered. Ask it again.</dd>
        </dl>
      </section>

      <section aria-labelledby="signin" className={styles.section}>
        <h2 id="signin">Signing in</h2>
        <p>
          Sign-in uses a link sent by email. You need your workspace ID, which is in the invitation
          from your administrator. Links expire after 15 minutes and work once.
        </p>
      </section>
    </Layout>
  );
}

export function Accessibility() {
  return (
    <Layout>
      <h1>Accessibility statement</h1>
      <p className={styles.lead}>
        This statement applies to the Firebrief web application. It was last reviewed on 11 November
        2026.
      </p>

      <section aria-labelledby="conformance" className={styles.section}>
        <h2 id="conformance">How accessible this is</h2>
        <p>
          Firebrief aims to meet WCAG 2.2 level AA. The interface is keyboard operable, has a visible
          focus indicator, works at 200% zoom, respects reduced motion and colour-scheme preferences,
          and announces answers and errors to screen readers.
        </p>
      </section>

      <section aria-labelledby="known" className={styles.section}>
        <h2 id="known">Known limitations</h2>
        <ul className={styles.list}>
          <li>
            Opening a quote in the source document uses a text fragment, which some browsers ignore.
            In those browsers the document opens at the top.
          </li>
          <li>The product has not yet been tested with a screen reader by an external auditor.</li>
        </ul>
      </section>

      <section aria-labelledby="report" className={styles.section}>
        <h2 id="report">Reporting a problem</h2>
        <p>
          If something is not accessible to you, email <a href="mailto:accessibility@firebrief.example">accessibility@firebrief.example</a>{" "}
          and describe what happened. We will reply within five working days.
        </p>
      </section>
    </Layout>
  );
}

export function SignedOut() {
  return (
    <Layout>
      <h1>You are signed out</h1>
      <p>Your session has ended. Nothing else changed.</p>
      <p>
        <Link to="/sign-in">Sign in again</Link>
      </p>
    </Layout>
  );
}

export function NotFound() {
  return (
    <Layout>
      <h1>Page not found</h1>
      <p>That address does not exist. It may have moved.</p>
      <p>
        <Link to="/">Go to the start page</Link>
      </p>
    </Layout>
  );
}
