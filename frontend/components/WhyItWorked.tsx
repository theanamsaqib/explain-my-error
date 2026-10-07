import { Lightbulb, Quote } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { WhyItWorked as Why } from "@/types/debug";

function Block({ n, title, children }: { n: number; title: string; children: string }) {
  return (
    <div className="rounded-md border border-border/80 bg-background/50 p-3.5">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="flex size-5 items-center justify-center rounded-full bg-primary/15 font-mono text-[11px] text-primary">{n}</span>
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <p className="text-sm leading-relaxed text-foreground/85">{children}</p>
    </div>
  );
}

/** The signature feature. Deliberately styled differently from every other panel. */
export function WhyItWorked({ why }: { why: Why }) {
  return (
    <section className="eme-rise overflow-hidden rounded-lg border border-primary/40 bg-gradient-to-b from-primary/[0.09] to-card shadow-[0_0_0_1px_rgba(245,177,74,0.06),0_12px_40px_-12px_rgba(245,177,74,0.18)]">
      <header className="flex items-center gap-2.5 border-b border-primary/25 px-4 py-3">
        <span className="flex size-8 items-center justify-center rounded-full bg-primary/15">
          <Lightbulb className="size-4 text-primary" />
        </span>
        <div>
          <h2 className="text-lg font-semibold leading-tight">Why Did My Fix Work?</h2>
          <p className="text-xs text-muted-foreground">So you can fix the next one yourself.</p>
        </div>
      </header>

      <div className="space-y-3 p-4">
        <Block n={1} title="What was wrong?">
          {why.what_was_wrong}
        </Block>
        <Block n={2} title="What changed?">
          {why.what_changed}
        </Block>
        <Block n={3} title="Why did it work?">
          {why.why_it_worked}
        </Block>

        {why.concepts.length > 0 && (
          <div>
            <h3 className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Concepts learned</h3>
            <div className="flex flex-wrap gap-2">
              {why.concepts.map((c) => (
                <Badge key={c} variant="default" className="px-2.5 py-1 text-[13px]">
                  {c}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {why.remember && (
          <div className="flex gap-2.5 rounded-md border border-primary/25 bg-primary/[0.07] p-3.5">
            <Quote className="mt-0.5 size-4 shrink-0 text-primary" />
            <div>
              <div className="mb-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-primary/80">Remember</div>
              <p className="text-sm font-medium leading-relaxed">{why.remember}</p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
