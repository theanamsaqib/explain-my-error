import { Check, CircleDashed, Footprints, Loader2, X } from "lucide-react";

import { CodeBlock } from "@/components/CodeBlock";
import { ExecutionResultView } from "@/components/ExecutionResult";
import { Panel } from "@/components/Panel";
import { cn } from "@/lib/utils";
import type { AttemptPhase, AttemptView, ToolCall } from "@/types/debug";

type StepState = "done" | "active" | "pending";

function Step({ label, state }: { label: string; state: StepState }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10.5px]",
        state === "done" && "border-border bg-muted/60 text-muted-foreground",
        state === "active" && "eme-pulse border-primary/50 bg-primary/10 text-primary",
        state === "pending" && "border-border/50 text-muted-foreground/40",
      )}
    >
      {state === "done" ? <Check className="size-3" /> : state === "active" ? <Loader2 className="size-3 animate-spin" /> : <CircleDashed className="size-3" />}
      {label}
    </span>
  );
}

function stepStates(a: AttemptView): [StepState, StepState, StepState] {
  const analyze: StepState = a.analyzed ? "done" : a.phase === "generating" ? "active" : "pending";
  const generate: StepState = a.phase === "generating" ? (a.analyzed ? "active" : "pending") : "done";
  const execute: StepState = a.phase === "running" ? "active" : a.phase === "failed" || a.phase === "passed" ? "done" : "pending";
  return [analyze, generate, execute];
}

function statusText(phase: AttemptPhase, n: number): { text: string; className: string } {
  switch (phase) {
    case "generating":
      return { text: n === 1 ? "Generating fix..." : "Generating improved fix...", className: "eme-pulse text-primary" };
    case "running":
      return { text: "Running code...", className: "eme-pulse text-primary" };
    case "failed":
      return { text: "✗ Failed", className: "text-destructive" };
    case "passed":
      return { text: "✓ Passed", className: "text-success" };
  }
}

export interface AttemptTrackerProps {
  attempts: AttemptView[];
  maxAttempts: number;
  running: boolean;
  statusMessage?: string;
  toolTrace?: ToolCall[];
}

/** "Debugging journey": the visible proof of the agent loop (act -> observe -> retry). */
export function AttemptTracker({ attempts, maxAttempts, running, statusMessage, toolTrace = [] }: AttemptTrackerProps) {
  const last = attempts[attempts.length - 1];
  const passed = last?.phase === "passed";
  const footer = running
    ? statusMessage || "Agent is working..."
    : passed
      ? `${attempts.length} attempt${attempts.length === 1 ? "" : "s"} required`
      : `Gave up after ${attempts.length} attempt${attempts.length === 1 ? "" : "s"} (limit ${maxAttempts})`;

  return (
    <Panel title="Debugging journey" icon={<Footprints className="size-3.5" />} tone={passed ? "success" : "default"} className="eme-rise">
      <ol className="relative space-y-4">
        {attempts.length > 1 && <span className="absolute bottom-3 left-[7px] top-3 w-px bg-border" aria-hidden />}
        {attempts.map((a) => {
          const [s1, s2, s3] = stepStates(a);
          const status = statusText(a.phase, a.number);
          const finished = a.phase === "failed" || a.phase === "passed";
          return (
            <li key={a.number} className="relative pl-7" data-testid={`attempt-${a.number}`}>
              <span
                className={cn(
                  "absolute left-0 top-1 size-[15px] rounded-full border-2 bg-card",
                  a.phase === "passed" && "border-success bg-success/30",
                  a.phase === "failed" && "border-destructive bg-destructive/30",
                  (a.phase === "generating" || a.phase === "running") && "eme-pulse border-primary",
                )}
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-semibold">Attempt {a.number}</span>
                <span className={cn("font-mono text-xs", status.className)}>{status.text}</span>
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <Step label="Analyze" state={s1} />
                <span className="text-muted-foreground/40">→</span>
                <Step label="Generate fix" state={s2} />
                <span className="text-muted-foreground/40">→</span>
                <Step label="Execute" state={s3} />
              </div>

              {a.rationale && <p className="mt-2 text-[13px] italic text-muted-foreground">“{a.rationale}”</p>}

              {a.phase === "failed" && a.attempt && (
                <div className="mt-2 rounded-md border border-destructive/25 bg-destructive/5 px-3 py-2">
                  <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Agent observed</div>
                  <div className="mt-0.5 font-mono text-[13px] text-destructive/90">{a.attempt.observation}</div>
                </div>
              )}

              {finished && a.attempt && (
                <details className="group mt-2">
                  <summary className="cursor-pointer list-none font-mono text-[11px] text-muted-foreground hover:text-foreground">
                    <span className="group-open:hidden">▸ show code and output</span>
                    <span className="hidden group-open:inline">▾ hide code and output</span>
                  </summary>
                  <div className="mt-2 space-y-2.5">
                    <CodeBlock code={a.attempt.code} maxHeight="14rem" />
                    <ExecutionResultView result={a.attempt.execution} />
                  </div>
                </details>
              )}
            </li>
          );
        })}
      </ol>

      <div className="mt-4 flex items-center gap-2 border-t border-border pt-3 font-mono text-xs">
        {running ? (
          <Loader2 className="size-3.5 animate-spin text-primary" />
        ) : passed ? (
          <Check className="size-3.5 text-success" />
        ) : (
          <X className="size-3.5 text-destructive" />
        )}
        <span className={cn(running ? "text-muted-foreground" : passed ? "text-success" : "text-destructive")}>{footer}</span>
      </div>

      {toolTrace.length > 0 && (
        <details className="mt-3 rounded-md border border-border/70">
          <summary className="cursor-pointer list-none px-3 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground">
            Agent tool calls ({toolTrace.length})
          </summary>
          <ul className="space-y-1 border-t border-border/70 p-3 font-mono text-[11.5px]">
            {toolTrace.map((t, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-2">
                <span className={cn("rounded px-1.5 py-0.5", t.ok ? "bg-muted text-primary" : "bg-destructive/10 text-destructive")}>
                  {t.tool}()
                </span>
                <span className="text-muted-foreground/60">{t.by === "agent" ? "agent" : "system"}</span>
                <span className="text-muted-foreground">{t.summary}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}
