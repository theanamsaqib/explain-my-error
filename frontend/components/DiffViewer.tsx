import { cn } from "@/lib/utils";
import type { DiffResult } from "@/types/debug";

/** Renders the backend's generate_diff output as a red / green diff. */
export function DiffViewer({ diff }: { diff: DiffResult }) {
  if (!diff.changed) {
    return <p className="font-mono text-xs text-muted-foreground">No changes: the fixed code is identical to the original.</p>;
  }

  return (
    <div className="overflow-hidden rounded-md border border-border bg-background">
      <div className="flex items-center gap-3 border-b border-border bg-elevated/50 px-3 py-1.5 font-mono text-[11px]">
        <span className="text-muted-foreground">original.py → fixed.py</span>
        <span className="text-success">+{diff.added}</span>
        <span className="text-destructive">−{diff.removed}</span>
      </div>
      <pre className="overflow-auto py-1.5 font-mono text-[12.5px] leading-5">
        {diff.lines.map((line, i) => {
          const prev = diff.lines[i - 1];
          const gap =
            prev && line.new_no !== null && prev.new_no !== null && line.new_no - prev.new_no > 1 && line.type !== "remove";
          return (
            <div key={i}>
              {gap && <div className="px-3 py-0.5 text-muted-foreground/40">⋯</div>}
              <div
                className={cn(
                  "flex min-w-max",
                  line.type === "add" && "bg-success/10 text-success",
                  line.type === "remove" && "bg-destructive/10 text-destructive",
                  line.type === "context" && "text-muted-foreground",
                )}
              >
                <span className="w-9 shrink-0 select-none pr-2 text-right opacity-50">{line.old_no ?? ""}</span>
                <span className="w-9 shrink-0 select-none pr-2 text-right opacity-50">{line.new_no ?? ""}</span>
                <span className="w-5 shrink-0 select-none text-center">
                  {line.type === "add" ? "+" : line.type === "remove" ? "-" : " "}
                </span>
                <code className="whitespace-pre pr-4">{line.text || " "}</code>
              </div>
            </div>
          );
        })}
      </pre>
    </div>
  );
}
