import { build } from "vite";
import react from "@vitejs/plugin-react";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const fox = process.argv.includes("--fox");
const outDir = path.join(root, "build", fox ? "fox-lantern" : "lamp-study");

const result = await build({
  configFile: false,
  root,
  base: "./",
  publicDir: false,
  plugins: [react()],
  resolve: { alias: { "@": path.join(root, "src") } },
  build: {
    write: false,
    outDir,
    emptyOutDir: false,
    assetsInlineLimit: Number.MAX_SAFE_INTEGER,
    cssCodeSplit: false,
    modulePreload: false,
    sourcemap: false,
    rollupOptions: {
      input: path.join(root, "docs", "concept", fox ? "fox-study.html" : "lamp-study.html"),
      output: { inlineDynamicImports: true },
    },
  },
});

if (Array.isArray(result) || !("output" in result)) {
  throw new Error("Expected one production build output");
}
const files = result.output;
const htmlFile = files.find((file) => file.fileName.endsWith(".html"));
if (!htmlFile || htmlFile.type !== "asset") {
  throw new Error("Vite did not produce the scene HTML");
}
const contents = (file) => file.type === "chunk"
  ? file.code
  : Buffer.from(file.source).toString("utf8");
const emitted = (url) => {
  const resolved = path.posix.normalize(path.posix.join(path.posix.dirname(htmlFile.fileName), url));
  const file = files.find((item) => item.fileName === resolved);
  if (!file) throw new Error(`Unresolved HTML resource: ${url}`);
  return contents(file);
};

let html = contents(htmlFile).replace(
  /<script\b[^>]*\bsrc="([^"]+)"[^>]*>\s*<\/script>/gi,
  (_, url) => `<script type="module">${emitted(url).replace(/<\/script/gi, "<\\/script")}</script>`,
);
html = html.replace(
  /<link\b(?=[^>]*\brel="stylesheet")(?=[^>]*\bhref="([^"]+)")[^>]*>/gi,
  (_, url) => `<style>${emitted(url).replace(/<\/style/gi, "<\\/style")}</style>`,
);

// A portable file must carry every resource, including future scene assets.
const resources = [...html.matchAll(/<(?:script|link|img|source|video|audio)\b[^>]*\b(?:src|href|poster)="([^"]+)"/gi)];
if (resources.some((match) => !match[1].startsWith("data:"))) {
  throw new Error("The scene still references an external resource");
}
const css = [...html.matchAll(/<style>([\s\S]*?)<\/style>/gi)].map((match) => match[1]).join("\n");
const cssUrls = [...css.matchAll(/url\(\s*(["']?)(.*?)\1\s*\)/gi)];
if (cssUrls.some((match) => !/^(?:data:|#)/i.test(match[2]))) {
  throw new Error("The scene still references an external CSS resource");
}

await mkdir(outDir, { recursive: true });
const destination = path.join(outDir, "index.html");
await writeFile(destination, html, "utf8");
console.log(`Standalone scene: ${destination} (${Buffer.byteLength(html)} bytes)`);
