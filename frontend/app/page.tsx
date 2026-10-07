"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Bug, FileCode2, Info, Loader2, Terminal } from "lucide-react";

import { ActionBar } from "@/components/ActionBar";
import { AttemptTracker } from "@/components/AttemptTracker";
import { CodeEditor } from "@/components/CodeEditor";
import { DebugHistory } from "@/components/DebugHistory";
import { ErrorInput } from "@/components/ErrorInput";
import { ExplanationPanel } from "@/components/ExplanationPanel";
import { FixPanel } from "@/components/FixPanel";
import { Panel } from "@/components/Panel";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { WhyItWorked } from "@/components/WhyItWorked";
import { ApiError, getHealth, getHistory, getSession, runDebug, streamDebug } from "@/lib/api";
import { EXAMPLES } from "@/lib/examples";
import type {
  Attempt,
  AttemptView,
  DebugRequest,
  DebugResponse,
  ExplanationMode,
  Health,
  HistoryItem,
  ToolCall,
} from "@/types/debug";

function toViews(attempts: Attempt[]): AttemptView[] {
  return attempts.map((a) => ({
    number: a.number,
    phase: a.success ? "passed" : "failed",
    analyzed: a.analyzed,
    rationale: a.rationale,
    attempt: a,
  }));
}

function upsert(list: AttemptView[], number: number, patch: Partial<AttemptView>): AttemptView[] {
  const exists = list.some((a) => a.number === number);
  const base: AttemptView = { number, phase: "generating", analyzed: number === 1, rationale: "" };
  return exists ? list.map((a) => (a.number === number ? { ...a, ...patch } : a)) : [...list, { ...base, ...patch }];
}

function messageOf(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof DOMException && e.name === "AbortError") return "Cancelled.";
  return "Something unexpected went wrong in the browser.";
}

export default function Home() {
  const first = EXAMPLES[0];
  const [code, setCode] = useState(first.code);
  const [error, setError] = useState(first.error);
  const [expected, setExpected] = useState(first.expectedOutput);
  const [style, setStyle] = useState<ExplanationMode>("cs_student");

  const [busy, setBusy] = useState<"explain" | "fix" | null>(null);
  const [explainRes, setExplainRes] = useState<DebugResponse | null>(null);
  const [fixRes, setFixRes] = useState<DebugResponse | null>(null);
  const [live, setLive] = useState<AttemptView[]>([]);
  const [liveTools, setLiveTools] = useState<ToolCall[]>([]);
  const [statusMsg, setStatusMsg] = useState("");
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [backendDown, setBackendDown] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await getHistory());
    } catch {
      /* history is optional; the main error banner covers connectivity */
    }
  }, []);

  useEffect(() => {
    getHealth()
      .then((h) => {
        setHealth(h);
        setBackendDown(false);
      })
      .catch(() => setBackendDown(true));
    getHistory()
      .then(setHistory)
      .catch(() => {
        /* the main error banner covers connectivity */
      });
    return () => abortRef.current?.abort();
  }, []);

  const request = (mode: "explain" | "fix"): DebugRequest => ({
    mode,
    code,
    error,
    explanation_mode: style,
    expected_output: expected.trim() ? expected : null,
  });

  const onExplain = async () => {
    setBusy("explain");
    setErrMsg(null);
    try {
      const res = await runDebug(request("explain"));
      setExplainRes(res);
      setActiveId(res.id);
    } catch (e) {
      setErrMsg(messageOf(e));
    } finally {
      setBusy(null);
      refreshHistory();
    }
  };

  const onFix = async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setBusy("fix");
    setErrMsg(null);
    setFixRes(null);
    setLive([]);
    setLiveTools([]);
    setStatusMsg("Starting the agent...");

    try {
      await streamDebug(
        request("fix"),
        (ev) => {
          switch (ev.type) {
            case "status":
              setStatusMsg(ev.message);
              break;
            case "tool_call":
              setLiveTools((t) => [...t, { tool: ev.tool, summary: ev.summary, ok: ev.ok, by: ev.by === "agent" ? "agent" : "orchestrator" }]);
              if (ev.tool === "analyze_code" && ev.by === "agent") {
                // the agent is analysing the new failure before its next attempt
                setLive((l) => l.map((a, i) => (i === l.length - 1 && a.phase === "generating" ? { ...a, analyzed: true } : a)));
              }
              break;
            case "attempt_started":
              setLive((l) => upsert(l, ev.attempt, {}));
              break;
            case "attempt_running":
              setLive((l) => upsert(l, ev.attempt, { phase: "running", rationale: ev.rationale }));
              break;
            case "attempt_result":
              setLive((l) =>
                upsert(l, ev.attempt, {
                  phase: ev.data.success ? "passed" : "failed",
                  analyzed: ev.data.analyzed,
                  rationale: ev.data.rationale,
                  attempt: ev.data,
                }),
              );
              break;
            case "result":
              setFixRes(ev.response);
              setActiveId(ev.response.id);
              break;
          }
        },
        controller.signal,
      );
    } catch (e) {
      setErrMsg(messageOf(e));
    } finally {
      setBusy(null);
      setLive([]);
      setLiveTools([]);
      setStatusMsg("");
      refreshHistory();
    }
  };

  const openSession = async (id: number) => {
    try {
      const s = await getSession(id);
      setCode(s.code);
      setError(s.error);
      setStyle(s.explanation_mode);
      setActiveId(id);
      setErrMsg(null);
      if (s.mode === "explain") {
        setExplainRes(s);
        setFixRes(null);
      } else {
        setFixRes(s);
        setExplainRes(null);
      }
    } catch (e) {
      setErrMsg(messageOf(e));
    }
  };

  const loadExample = (id: string) => {
    const ex = EXAMPLES.find((e) => e.id === id);
    if (!ex) return;
    setCode(ex.code);
    setError(ex.error);
    setExpected(ex.expectedOutput);
    setExplainRes(null);
    setFixRes(null);
    setErrMsg(null);
    setActiveId(null);
  };

  // Only highlight when the editor still holds the code that was explained.
  const highlightLines = useMemo(
    () => (explainRes?.explanation && explainRes.code === code ? explainRes.explanation.problematic_lines : []),
    [explainRes, code],
  );

  const attemptViews = busy === "fix" ? live : fixRes ? toViews(fixRes.attempts) : [];
  const tools = busy === "fix" ? liveTools : (fixRes?.tool_trace ?? []);
  const warnings = [...(explainRes?.warnings ?? []), ...(fixRes?.warnings ?? [])];
  const finalAttempt = fixRes?.attempts[fixRes.attempts.length - 1];
  const nothingYet = !explainRes && !fixRes && !busy && !errMsg;
  const noError = [explainRes, fixRes].find((r) => r?.status === "no_error");
  const fixBlocked = health && !health.llm_configured ? "Fixing needs an LLM key. Set OPENAI_API_KEY in backend/.env." : undefined;

  return (
    <div className="mx-auto w-full max-w-[1640px] px-4 pb-10 pt-6 sm:px-6">
      {/* ------------------------------------------------------------ header */}
      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            <Bug className="size-3.5 text-primary" />
            agentic ai debugger
          </div>
          <h1 className="text-3xl font-semibold leading-[1.1] tracking-tight sm:text-4xl xl:text-[2.6rem]">
            Explain My Error <span className="text-primary">{"Like I'm Losing My Mind"}</span>
          </h1>
          <p className="mt-2 font-mono text-sm text-muted-foreground">
            {"Your code is broken. Let's figure out why."}
            <span className="eme-caret" aria-hidden />
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          {backendDown ? (
            <Badge variant="destructive">backend offline</Badge>
          ) : health ? (
            <>
              <Badge variant={health.llm_configured ? "success" : "destructive"}>
                {health.llm_configured ? `● agent ready · ${health.model}` : "● no LLM key (static explain only)"}
              </Badge>
              <Badge variant="muted">sandbox: {health.execution_backend}</Badge>
              <Badge variant="muted">max {health.max_attempts} attempts</Badge>
            </>
          ) : (
            <Badge variant="muted">connecting...</Badge>
          )}
        </div>
      </header>

      <main className="grid gap-4 lg:grid-cols-2 xl:grid-cols-[250px_minmax(0,1fr)_minmax(0,1.08fr)]">
        {/* ---------------------------------------------------------- history */}
        <aside className="order-3 min-w-0 lg:col-span-2 xl:order-1 xl:col-span-1 xl:self-start">
          <DebugHistory items={history} activeId={activeId} onSelect={openSession} />
        </aside>

        {/* -------------------------------------------------------- workbench */}
        <section className="order-1 min-w-0 space-y-4 xl:order-2">
          <Panel
            title="main.py"
            icon={<FileCode2 className="size-3.5 text-primary" />}
            right={
              <Select value="" onValueChange={loadExample}>
                <SelectTrigger className="h-7 w-auto gap-1.5 border-border/70 px-2 text-xs" aria-label="Load example">
                  <SelectValue placeholder="Load example..." />
                </SelectTrigger>
                <SelectContent align="end">
                  {EXAMPLES.map((ex) => (
                    <SelectItem key={ex.id} value={ex.id}>
                      {ex.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            }
            bodyClassName="space-y-4 p-3.5"
          >
            <CodeEditor value={code} onChange={setCode} highlightLines={highlightLines} />
            <ErrorInput error={error} onErrorChange={setError} expected={expected} onExpectedChange={setExpected} />
            <ActionBar
              style={style}
              onStyleChange={setStyle}
              busy={busy}
              disabled={!code.trim() || backendDown}
              onExplain={onExplain}
              onFix={onFix}
              fixDisabledReason={fixBlocked}
            />
          </Panel>
          <p className="px-1 text-[11px] leading-relaxed text-muted-foreground/70">
            College project. Code runs in a restricted subprocess (or Docker) with a timeout, but this is not a production-grade sandbox.
          </p>
        </section>

        {/* ---------------------------------------------------------- results */}
        <section className="order-2 min-w-0 space-y-4 xl:order-3" aria-live="polite">
          {errMsg && (
            <div role="alert" className="flex items-start gap-2.5 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
              <span>{errMsg}</span>
            </div>
          )}

          {warnings.length > 0 && (
            <div className="space-y-1.5 rounded-lg border border-primary/30 bg-primary/[0.06] px-4 py-3 text-[13px]">
              {warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2">
                  <Info className="mt-0.5 size-3.5 shrink-0 text-primary" />
                  <span className="text-foreground/85">{w}</span>
                </div>
              ))}
            </div>
          )}

          {noError && (
            <Panel title="No error found" icon={<Info className="size-3.5" />} tone="success">
              <p className="whitespace-pre-wrap font-mono text-sm">{noError.message}</p>
            </Panel>
          )}

          {busy === "explain" && (
            <Panel title="Reading your code" icon={<Loader2 className="size-3.5 animate-spin" />}>
              <p className="eme-pulse font-mono text-sm text-muted-foreground">Analyzing, then writing the explanation...</p>
            </Panel>
          )}

          {explainRes?.explanation && <ExplanationPanel explanation={explainRes.explanation} />}

          {(busy === "fix" || attemptViews.length > 0) && (
            <AttemptTracker
              attempts={attemptViews}
              maxAttempts={fixRes?.max_attempts ?? health?.max_attempts ?? 3}
              running={busy === "fix"}
              statusMessage={statusMsg}
              toolTrace={tools}
            />
          )}

          {busy !== "fix" && fixRes?.fix && (
            <FixPanel fix={fixRes.fix} finalAttempt={finalAttempt} message={fixRes.message} onApply={setCode} />
          )}

          {busy !== "fix" && fixRes?.status === "failed" && !fixRes.fix && (
            <Panel title="Fix failed" tone="danger">
              <p className="text-sm">{fixRes.message}</p>
            </Panel>
          )}

          {busy !== "fix" && fixRes?.why_it_worked && <WhyItWorked why={fixRes.why_it_worked} />}

          {nothingYet && (
            <div className="flex min-h-[22rem] flex-col items-center justify-center rounded-lg border border-dashed border-border px-6 text-center">
              <Terminal className="mb-3 size-8 text-muted-foreground/40" />
              <p className="font-mono text-sm text-muted-foreground">$ waiting for a bug...</p>
              <p className="mt-2 max-w-sm text-xs leading-relaxed text-muted-foreground/70">
                Paste broken Python and its error, then hit <strong className="text-foreground/80">Explain My Error</strong> to understand
                it, or <strong className="text-foreground/80">Fix My Code</strong> to watch the agent fix it, run it and prove it works.
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
