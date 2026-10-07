"use client";

import { BookOpen, History, Wrench } from "lucide-react";

import { Panel } from "@/components/Panel";
import { cn, timeAgo } from "@/lib/utils";
import type { HistoryItem } from "@/types/debug";

interface DebugHistoryProps {
  items: HistoryItem[];
  activeId: number | null;
  onSelect: (id: number) => void;
}

const STATUS_DOT: Record<string, string> = {
  fixed: "bg-success",
  failed: "bg-destructive",
  explained: "bg-primary",
  no_error: "bg-muted-foreground",
  error: "bg-destructive",
};

export function DebugHistory({ items, activeId, onSelect }: DebugHistoryProps) {
  return (
    <Panel title="Recent debug sessions" icon={<History className="size-3.5" />} bodyClassName="p-1.5">
      {items.length === 0 ? (
        <p className="px-2.5 py-4 font-mono text-xs leading-relaxed text-muted-foreground">
          {"// nothing yet."}
          <br />
          {"// your bugs will show up here."}
        </p>
      ) : (
        <ul className="max-h-[28rem] space-y-0.5 overflow-y-auto">
          {items.map((it) => (
            <li key={it.id}>
              <button
                type="button"
                onClick={() => onSelect(it.id)}
                className={cn(
                  "w-full rounded-md px-2.5 py-2 text-left transition-colors hover:bg-accent",
                  activeId === it.id && "bg-accent ring-1 ring-primary/30",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className={cn("size-2 shrink-0 rounded-full", STATUS_DOT[it.status] ?? "bg-muted-foreground")} title={it.status} />
                  <span className="truncate font-mono text-[13px] font-medium">{it.error_type || "Unknown"}</span>
                  {it.mode === "fix" ? (
                    <Wrench className="ml-auto size-3 shrink-0 text-muted-foreground" aria-label="fix" />
                  ) : (
                    <BookOpen className="ml-auto size-3 shrink-0 text-muted-foreground" aria-label="explain" />
                  )}
                </div>
                <div className="mt-0.5 truncate pl-4 text-[11.5px] text-muted-foreground">{it.preview}</div>
                <div className="pl-4 font-mono text-[10px] text-muted-foreground/60">
                  {it.mode} · {it.status.replace("_", " ")} · {timeAgo(it.created_at)}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
