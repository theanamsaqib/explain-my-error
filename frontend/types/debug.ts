// Mirrors backend/app/models/schemas.py. Keep the two in sync.

export type ExplanationMode = "eli5" | "cs_student" | "interview" | "technical";
export type DebugMode = "explain" | "fix";
export type DebugStatus = "explained" | "fixed" | "failed" | "no_error" | "error";

export interface DebugRequest {
  mode: DebugMode;
  code: string;
  error: string;
  language?: string;
  explanation_mode: ExplanationMode;
  expected_output?: string | null;
}

export interface ExecutionResult {
  success: boolean;
  stdout: string;
  stderr: string;
  exit_code: number | null;
  timed_out: boolean;
  output_truncated: boolean;
  duration_ms: number;
  note: string;
}

export interface DiffLine {
  type: "add" | "remove" | "context";
  text: string;
  old_no: number | null;
  new_no: number | null;
}

export interface DiffResult {
  unified_diff: string;
  lines: DiffLine[];
  added: number;
  removed: number;
  changed: boolean;
}

export interface Explanation {
  error_type: string;
  summary: string;
  explanation: string;
  concept: string;
  problematic_lines: number[];
  problematic_code: string;
  example: string | null;
  source: "llm" | "static";
}

export interface Attempt {
  number: number;
  analyzed: boolean;
  rationale: string;
  code: string;
  execution: ExecutionResult;
  success: boolean;
  observation: string;
  source: "agent" | "orchestrator";
}

export interface FixResult {
  diagnosis: string;
  fixed_code: string;
  changes: string[];
  reasoning: string;
  diff: DiffResult | null;
  verified: boolean;
}

export interface ToolCall {
  tool: string;
  summary: string;
  ok: boolean;
  by: "agent" | "orchestrator";
}

export interface WhyItWorked {
  what_was_wrong: string;
  what_changed: string;
  why_it_worked: string;
  concepts: string[];
  remember: string;
}

export interface DebugResponse {
  id: number | null;
  mode: DebugMode;
  status: DebugStatus;
  error_type: string;
  message: string;
  explanation: Explanation | null;
  fix: FixResult | null;
  attempts: Attempt[];
  max_attempts: number;
  why_it_worked: WhyItWorked | null;
  tool_trace: ToolCall[];
  warnings: string[];
  code: string;
  error: string;
  explanation_mode: ExplanationMode;
}

export interface HistoryItem {
  id: number;
  created_at: string;
  mode: DebugMode;
  status: DebugStatus;
  error_type: string;
  preview: string;
}

export interface Health {
  status: string;
  llm_configured: boolean;
  model: string;
  execution_backend: string;
  max_attempts: number;
}

// ---- Server-Sent Events from POST /api/debug/stream
export type StreamEvent =
  | { type: "status"; stage: string; message: string }
  | { type: "tool_call"; tool: string; summary: string; ok: boolean; by: string }
  | { type: "attempt_started"; attempt: number }
  | { type: "attempt_running"; attempt: number; rationale: string; code: string }
  | { type: "attempt_result"; attempt: number; data: Attempt }
  | { type: "result"; response: DebugResponse }
  | { type: "error"; error: { code: string; message: string } };

// ---- UI-only: one row in the "Debugging journey", live or finished
export type AttemptPhase = "generating" | "running" | "failed" | "passed";

export interface AttemptView {
  number: number;
  phase: AttemptPhase;
  analyzed: boolean;
  rationale: string;
  attempt?: Attempt;
}

export const MODE_LABELS: Record<ExplanationMode, string> = {
  eli5: "I'm 5",
  cs_student: "CS Student",
  interview: "Interview Mode",
  technical: "Technical",
};
