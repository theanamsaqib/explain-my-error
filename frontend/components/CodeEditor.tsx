"use client";

import { useEffect, useRef, useState } from "react";
import Editor, { loader, type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";

import { Textarea } from "@/components/ui/textarea";

// Serve Monaco from /public/monaco (copied by scripts/copy-monaco.mjs): works offline, no CDN.
loader.config({ paths: { vs: "/monaco/vs" } });

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  /** Lines (1-based) the agent flagged as the root cause; highlighted red in the editor. */
  highlightLines?: number[];
  height?: number;
}

export function CodeEditor({ value, onChange, highlightLines = [], height = 340 }: CodeEditorProps) {
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);
  const decorationsRef = useRef<Monaco.editor.IEditorDecorationsCollection | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const highlightKey = highlightLines.join(",");

  // If Monaco's assets cannot be loaded, fall back to a plain textarea so the app still works.
  useEffect(() => {
    if (ready) return;
    const timer = setTimeout(() => setFailed(true), 8000);
    return () => clearTimeout(timer);
  }, [ready]);

  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!ready || !editor || !monaco) return;
    const lines = highlightKey ? highlightKey.split(",").map(Number) : [];
    decorationsRef.current?.clear();
    decorationsRef.current = editor.createDecorationsCollection(
      lines.map((line) => ({
        range: new monaco.Range(line, 1, line, 1),
        options: { isWholeLine: true, className: "eme-error-line", glyphMarginClassName: "eme-error-glyph" },
      })),
    );
    if (lines.length) editor.revealLineInCenterIfOutsideViewport(lines[0]);
  }, [highlightKey, ready]);

  const onMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    setReady(true);
  };

  if (failed && !ready) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">
          The code editor could not load, so here is a plain text box instead.
        </p>
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          className="font-mono text-[13px] leading-5"
          style={{ height }}
          aria-label="Python code"
        />
      </div>
    );
  }

  return (
    <div style={{ height }} className="overflow-hidden rounded-md border border-border">
      <Editor
        height="100%"
        defaultLanguage="python"
        language="python"
        theme="eme-dark"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        onMount={onMount}
        beforeMount={(monaco) => {
          monaco.editor.defineTheme("eme-dark", {
            base: "vs-dark",
            inherit: true,
            rules: [],
            colors: {
              "editor.background": "#0e0e11",
              "editorGutter.background": "#0e0e11",
              "editor.lineHighlightBackground": "#16161b",
              "editorLineNumber.foreground": "#4a4a55",
              "editorLineNumber.activeForeground": "#a0a0ab",
              "editor.selectionBackground": "#f5b14a33",
              "editorCursor.foreground": "#f5b14a",
            },
          });
        }}
        loading={<div className="p-4 font-mono text-xs text-muted-foreground">loading editor...</div>}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          lineHeight: 20,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace",
          glyphMargin: true,
          lineNumbers: "on",
          lineNumbersMinChars: 3,
          folding: false,
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 4,
          insertSpaces: true,
          padding: { top: 12, bottom: 12 },
          overviewRulerLanes: 0,
          renderLineHighlight: "line",
          smoothScrolling: true,
          ariaLabel: "Python code",
        }}
      />
    </div>
  );
}
