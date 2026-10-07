import { Clock, Hash, Scissors, TimerOff } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ExecutionResult } from "@/types/debug";

function Stream({ label, text, tone }: { label: string; text: string; tone: "out" | "err" }) {
  return (
    <div>
      <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
      <pre
        className={cn(
          "max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md border bg-background p-2.5 font-mono text-xs leading-5",
          tone === "err" ? "border-destructive/25 text-destructive/90" : "border-border text-foreground/90",
        )}
      >
        {text}
      </pre>
    </div>
  );
}

/** What the execute_python tool returned: stdout, stderr, exit code, timeout. */
export function ExecutionResultView({ result }: { result: ExecutionResult }) {
  const empty = !result.stdout.trim() && !result.stderr.trim();
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={result.success ? "success" : "destructive"} className="font-mono">
          <Hash className="size-3" />
          exit {result.exit_code ?? "n/a"}
        </Badge>
        <Badge variant="muted" className="font-mono">
          <Clock className="size-3" />
          {result.duration_ms} ms
        </Badge>
        {result.timed_out && (
          <Badge variant="destructive">
            <TimerOff className="size-3" />
            timed out
          </Badge>
        )}
        {result.output_truncated && (
          <Badge variant="muted">
            <Scissors className="size-3" />
            output truncated
          </Badge>
        )}
      </div>
      {result.stdout.trim() && <Stream label="stdout" text={result.stdout} tone="out" />}
      {result.stderr.trim() && <Stream label="stderr" text={result.stderr} tone="err" />}
      {result.note && <p className="text-xs text-muted-foreground">{result.note}</p>}
      {empty && !result.note && <p className="font-mono text-xs text-muted-foreground">(no output)</p>}
    </div>
  );
}
