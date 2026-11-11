/** Render the public pages to static HTML. They ship without JavaScript. */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const web = join(root, "..");
const dist = join(web, "dist");
const site = "https://firebrief.example";

const pages = [
  {
    path: "/",
    file: "index.html",
    title: "Firebrief — answers about UK fire safety guidance, with the quotes",
    description:
      "Ask a question about UK fire safety guidance and get an answer with verified quotes, or an explanation of why it cannot be answered.",
  },
  {
    path: "/about",
    file: "about/index.html",
    title: "How Firebrief verifies answers",
    description:
      "How Firebrief searches UK fire safety guidance, requires quotes, verifies them against the source, and withholds answers it cannot support.",
  },
  {
    path: "/help",
    file: "help/index.html",
    title: "Help — asking questions and understanding refusals",
    description:
      "How to ask a good question in Firebrief, what each refusal means, and how signing in works.",
  },
  {
    path: "/accessibility",
    file: "accessibility/index.html",
    title: "Accessibility statement — Firebrief",
    description:
      "Firebrief's accessibility statement: conformance with WCAG 2.2 AA, known limitations, and how to report a problem.",
  },
];

const template = await readFile(join(dist, "index.html"), "utf8");

// The public pages replace index.html. The app needs its own shell with the bundle, so
// keep a copy before anything is overwritten; the server rewrites app routes to it.
await writeFile(join(dist, "app.html"), template);
const { render } = await import(pathToFileURL(join(web, "dist-ssr/entry-server.js")).href);

for (const page of pages) {
  const markup = render(page.path);
  const html = template
    .replace(/<title>.*?<\/title>/, `<title>${page.title}</title>`)
    .replace(
      /<meta name="description"[^>]*>/,
      `<meta name="description" content="${page.description}" />`,
    )
    .replace(/<meta name="robots"[^>]*>/, "")
    .replace(/<link rel="canonical"[^>]*>/, `<link rel="canonical" href="${site}${page.path}" />`)
    .replace(
      /<head>/,
      `<head>
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="Firebrief" />
    <meta property="og:title" content="${page.title}" />
    <meta property="og:description" content="${page.description}" />
    <meta property="og:url" content="${site}${page.path}" />
    <meta name="twitter:card" content="summary" />`,
    )
    .replace(/<div id="root"><\/div>/, `<div id="root">${markup}</div>`)
    .replace(/<script type="module"[^>]*><\/script>/, "");

  const target = join(dist, page.file);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
  console.log(`prerendered ${page.path}`);
}

await writeFile(
  join(dist, "sitemap.xml"),
  `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${pages.map((page) => `  <url><loc>${site}${page.path}</loc></url>`).join("\n")}
</urlset>
`,
);

// App routes are noindex via a meta tag and an X-Robots-Tag header; disallowing them in
// robots.txt would stop crawlers from seeing the noindex at all.
await writeFile(join(dist, "robots.txt"), `User-agent: *\nAllow: /\n\nSitemap: ${site}/sitemap.xml\n`);
console.log("sitemap and robots written");
