"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { cn } from "@/lib/utils";

interface CodeBlockProps {
  code: string;
  /** 1-based line numbers (in the numbering shown) to highlight in red */
  highlight?: number[];
  /** explicit line numbers, one per line of `code` (default 1..n) */
  numbers?: number[];
  copyable?: boolean;
  className?: string;
  maxHeight?: string;
}

export function CodeBlock({ code, highlight = [], numbers, copyable = false, className, maxHeight = "20rem" }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const lines = code.replace(/\n$/, "").split("\n");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* clipboard unavailable (insecure context): ignore */
    }
  };

  return (
    <div className={cn("group relative rounded-md border border-border bg-background", className)}>
      <pre className="overflow-auto py-2 font-mono text-[12.5px] leading-5" style={{ maxHeight }}>
        {lines.map((text, i) => {
          const no = numbers?.[i] ?? i + 1;
          const hl = highlight.includes(no);
          return (
            <div key={i} className={cn("flex min-w-max px-0", hl && "bg-destructive/12")}>
              <span
                className={cn(
                  "w-10 shrink-0 select-none pr-3 text-right text-muted-foreground/50",
                  hl && "text-destructive/80",
                )}
              >
                {no}
              </span>
              <code className="whitespace-pre pr-4 text-foreground/90">{text || " "}</code>
            </div>
          );
        })}
      </pre>
      {copyable && (
        <button
          type="button"
          onClick={copy}
          aria-label="Copy code"
          className="absolute right-2 top-2 rounded border border-border bg-elevated p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus-visible:opacity-100 group-hover:opacity-100"
        >
          {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
        </button>
      )}
    </div>
  );
}
