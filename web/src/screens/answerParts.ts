import type { RefusalReason } from "../lib/api";

export const REFUSAL_COPY: Record<RefusalReason, { title: string; body: string; next: string }> = {
  no_sources: {
    title: "The guidance we hold does not cover this",
    body: "We could not find anything in the guidance that answers this question.",
    next: "Try naming the building type, the regulation, or the specific requirement.",
  },
  insufficient_evidence: {
    title: "The sources do not answer this question",
    body: "We found relevant guidance, but it does not settle what you asked.",
    next: "Try asking about one specific requirement at a time.",
  },
  unverified: {
    title: "We could not verify every quote",
    body: "An answer was drafted, but at least one quote did not match the guidance, so we are not showing it.",
    next: "Try a narrower question, or check the sources below yourself.",
  },
  truncated: {
    title: "The answer was cut off",
    body: "The answer stopped before it finished, so it could not be checked.",
    next: "Try a narrower question.",
  },
  budget_exhausted: {
    title: "This would exceed your usage limit",
    body: "Your organisation's limit for this period does not leave room for this question.",
    next: "Wait for the limit to reset, or ask your administrator to raise it.",
  },
  budget_unavailable: {
    title: "Usage checks are unavailable",
    body: "We could not check your usage, so nothing was attempted and nothing was charged.",
    next: "Try again in a moment.",
  },
  model_unavailable: {
    title: "Firebrief is temporarily unavailable",
    body: "The answer service did not respond, so nothing was charged.",
    next: "Try again in a moment.",
  },
  duplicate_request: {
    title: "This question was already sent",
    body: "A request with this identifier has already been answered.",
    next: "Ask it again to get a fresh answer.",
  },
};

export function markerSources(seen: number[]): string {
  return seen.map((n) => `[${n}]`).join(" ");
}
