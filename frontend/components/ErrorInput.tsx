"use client";

import { Textarea } from "@/components/ui/textarea";

interface ErrorInputProps {
  error: string;
  onErrorChange: (v: string) => void;
  expected: string;
  onExpectedChange: (v: string) => void;
}

export function ErrorInput({ error, onErrorChange, expected, onExpectedChange }: ErrorInputProps) {
  return (
    <div className="space-y-3">
      <div>
        <label htmlFor="error-input" className="mb-1.5 flex items-baseline justify-between font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          <span>Error output</span>
          <span className="normal-case tracking-normal text-muted-foreground/70">
            empty? I will run your code to find the error
          </span>
        </label>
        <Textarea
          id="error-input"
          value={error}
          onChange={(e) => onErrorChange(e.target.value)}
          placeholder="Paste your error message..."
          spellCheck={false}
          rows={5}
          className="font-mono text-[12.5px] leading-5 text-destructive/90"
        />
      </div>

      <details className="group rounded-md border border-border/70 bg-background/40">
        <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground">
          <span>Expected output (optional)</span>
          <span className="normal-case tracking-normal text-muted-foreground/70">
            {expected.trim() ? "set: a fix only counts if stdout matches" : "tighten what counts as fixed"}
          </span>
        </summary>
        <div className="border-t border-border/70 p-3">
          <Textarea
            value={expected}
            onChange={(e) => onExpectedChange(e.target.value)}
            placeholder="What should the program print? Needed for bugs that do not crash."
            spellCheck={false}
            rows={3}
            className="min-h-0 font-mono text-[12.5px] leading-5"
            aria-label="Expected output"
          />
        </div>
      </details>
    </div>
  );
}
