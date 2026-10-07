"use client";

import { CheckCircle2, FileCode2, XCircle } from "lucide-react";

import { CodeBlock } from "@/components/CodeBlock";
import { DiffViewer } from "@/components/DiffViewer";
import { ExecutionResultView } from "@/components/ExecutionResult";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Attempt, FixResult } from "@/types/debug";

interface FixPanelProps {
  fix: FixResult;
  finalAttempt?: Attempt;
  message: string;
  onApply: (code: string) => void;
}

export function FixPanel({ fix, finalAttempt, message, onApply }: FixPanelProps) {
  const verified = fix.verified;

  return (
    <Panel
      title="Proposed fix"
      icon={<FileCode2 className="size-3.5" />}
      tone={verified ? "success" : "danger"}
      className="eme-rise"
      right={
        <Button size="sm" variant="ghost" onClick={() => onApply(fix.fixed_code)}>
          Apply to editor
        </Button>
      }
    >
      <div className="space-y-5">
        {(fix.diagnosis || fix.changes.length > 0) && (
          <div className="space-y-2">
            {fix.diagnosis && <p className="text-sm text-foreground/90">{fix.diagnosis}</p>}
            {fix.changes.length > 0 && (
              <ul className="list-disc space-y-1 pl-5 text-[13px] text-muted-foreground marker:text-primary/70">
                {fix.changes.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        <CodeBlock code={fix.fixed_code} copyable maxHeight="18rem" />

        <div>
          <h3 className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Difference</h3>
          {fix.diff ? <DiffViewer diff={fix.diff} /> : <p className="text-xs text-muted-foreground">No diff available.</p>}
        </div>

        <div>
          <h3 className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Verification</h3>
          <div
            className={cn(
              "flex items-center gap-3 rounded-md border px-4 py-3",
              verified ? "border-success/40 bg-success/10" : "border-destructive/40 bg-destructive/10",
            )}
            role="status"
          >
            {verified ? <CheckCircle2 className="size-6 text-success" /> : <XCircle className="size-6 text-destructive" />}
            <div>
              <div className={cn("font-mono text-base font-semibold tracking-wide", verified ? "text-success" : "text-destructive")}>
                {verified ? "✓ FIX VERIFIED" : "✗ FIX FAILED"}
              </div>
              <div className="text-xs text-muted-foreground">{message}</div>
            </div>
          </div>
          {finalAttempt && (
            <div className="mt-3">
              <ExecutionResultView result={finalAttempt.execution} />
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
