import ReactMarkdown from "react-markdown";

import { cn } from "@/lib/utils";

/** Renders LLM markdown safely (react-markdown does not render raw HTML). */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("space-y-3 text-sm leading-relaxed text-foreground/90", className)}>
      <ReactMarkdown
        components={{
          p: ({ children }) => <p>{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
          em: ({ children }) => <em className="text-foreground/80">{children}</em>,
          code: ({ children }) => (
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-primary">{children}</code>
          ),
          pre: ({ children }) => (
            <pre className="overflow-x-auto rounded-md border border-border bg-background p-3 font-mono text-xs [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-foreground/90">
              {children}
            </pre>
          ),
          ul: ({ children }) => <ul className="list-disc space-y-1 pl-5 marker:text-primary/70">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal space-y-1 pl-5 marker:text-primary/70">{children}</ol>,
          h1: ({ children }) => <h3 className="font-semibold text-foreground">{children}</h3>,
          h2: ({ children }) => <h3 className="font-semibold text-foreground">{children}</h3>,
          h3: ({ children }) => <h4 className="font-semibold text-foreground">{children}</h4>,
          a: ({ children }) => <span className="underline">{children}</span>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
