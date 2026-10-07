// Copies Monaco's prebuilt assets into public/ so the editor works offline (no CDN needed).
import { cpSync, existsSync, mkdirSync } from "node:fs";

const src = "node_modules/monaco-editor/min/vs";
const dest = "public/monaco/vs";

if (!existsSync(src)) {
  console.warn("[copy-monaco] monaco-editor not installed yet, skipping.");
} else {
  mkdirSync("public/monaco", { recursive: true });
  cpSync(src, dest, { recursive: true });
  console.log("[copy-monaco] copied Monaco assets to", dest);
}
