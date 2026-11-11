/** Turning machine values into the words a busy reader needs. */

export function retryTime(seconds: number, now = new Date()): string {
  const at = new Date(now.getTime() + seconds * 1000);
  return at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

/** A text fragment for a quote, so the document opens near the passage where it is supported. */
export function quoteFragment(quote: string): string {
  const words = quote.trim().split(/\s+/).slice(0, 8).join(" ");
  if (!words) return "";
  return `#:~:text=${encodeURIComponent(words)}`;
}

export function sourceHref(url: string, quote?: string): string {
  const fragment = quote ? quoteFragment(quote) : "";
  const base = fragment ? url.split("#")[0] : url;
  return `${base}${fragment}`;
}

export function editionLine(edition: string): string {
  return `Edition ${edition}`;
}
