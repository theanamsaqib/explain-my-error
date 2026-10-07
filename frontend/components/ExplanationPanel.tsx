import { BookOpen, Lightbulb } from "lucide-react";

import { CodeBlock } from "@/components/CodeBlock";
import { Markdown } from "@/components/Markdown";
import { Panel } from "@/components/Panel";
import { Badge } from "@/components/ui/badge";
import type { Explanation } from "@/types/debug";

/** "123 | code" rows produced by the backend -> separate numbers and code for CodeBlock. */
function parseSnippet(snippet: string): { code: string; numbers: number[] } {
  const numbers: number[] = [];
  const code: string[] = [];
  for (const row of snippet.split("\n")) {
    const m = /^\s*(\d+) \| ?(.*)$/.exec(row);
    if (!m) continue;
    numbers.push(Number(m[1]));
    code.push(m[2]);
  }
  return { code: code.join("\n"), numbers };
}

export function ExplanationPanel({ explanation }: { explanation: Explanation }) {
  const snippet = parseSnippet(explanation.problematic_code);

  return (
    <Panel
      title="What went wrong?"
      icon={<BookOpen className="size-3.5" />}
      right={
        explanation.source === "static" ? (
          <Badge variant="muted" title="The LLM was unavailable, so this comes from the built-in static analysis.">
            static analysis only
          </Badge>
        ) : undefined
      }
      className="eme-rise"
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <div>
            <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Error type</div>
            <Badge variant="destructive" className="font-mono text-sm">
              {explanation.error_type}
            </Badge>
          </div>
          {explanation.concept && (
            <div>
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Concept</div>
              <Badge variant="default" className="gap-1.5 text-sm">
                <Lightbulb className="size-3.5" />
                {explanation.concept}
              </Badge>
            </div>
          )}
        </div>

        <p className="border-l-2 border-primary/70 pl-3 text-[15px] leading-relaxed text-foreground">{explanation.summary}</p>

        <Markdown>{explanation.explanation}</Markdown>

        {snippet.code && (
          <div>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              Problematic code
            </div>
            <CodeBlock code={snippet.code} numbers={snippet.numbers} highlight={snippet.numbers} maxHeight="12rem" />
          </div>
        )}

        {explanation.example && (
          <div>
            <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">Example</div>
            <CodeBlock code={explanation.example} maxHeight="12rem" />
          </div>
        )}
      </div>
    </Panel>
  );
}
