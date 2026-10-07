import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface PanelProps {
  title: string;
  icon?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  tone?: "default" | "success" | "danger" | "accent";
}

const TONES = {
  default: "border-border",
  success: "border-success/30",
  danger: "border-destructive/30",
  accent: "border-primary/40",
} as const;

/** A titled IDE-style panel. The mono, uppercase title bar is what makes the UI feel like a tool. */
export function Panel({ title, icon, right, children, className, bodyClassName, tone = "default" }: PanelProps) {
  return (
    <section className={cn("overflow-hidden rounded-lg border bg-card", TONES[tone], className)}>
      <header className="flex items-center justify-between gap-3 border-b border-border/80 bg-elevated/60 px-3.5 py-2">
        <h2 className="flex items-center gap-2 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
          {icon}
          {title}
        </h2>
        {right}
      </header>
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}
