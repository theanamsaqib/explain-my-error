"use client";

import { Loader2, Search, Wrench } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MODE_LABELS, type DebugMode, type ExplanationMode } from "@/types/debug";

interface ActionBarProps {
  style: ExplanationMode;
  onStyleChange: (v: ExplanationMode) => void;
  busy: DebugMode | null;
  disabled: boolean;
  onExplain: () => void;
  onFix: () => void;
  fixDisabledReason?: string;
}

const STYLE_HINTS: Record<ExplanationMode, string> = {
  eli5: "Explain like I'm 5",
  cs_student: "Explain like I'm a CS student",
  interview: "Explain like I'm preparing for an interview",
  technical: "Technical / Stack Overflow style",
};

export function ActionBar({ style, onStyleChange, busy, disabled, onExplain, onFix, fixDisabledReason }: ActionBarProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
      <div className="sm:w-52">
        <label className="mb-1.5 block font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
          Explanation mode
        </label>
        <Select value={style} onValueChange={(v) => onStyleChange(v as ExplanationMode)} disabled={busy !== null}>
          <SelectTrigger aria-label="Explanation mode" title={STYLE_HINTS[style]}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(MODE_LABELS) as ExplanationMode[]).map((m) => (
              <SelectItem key={m} value={m}>
                {MODE_LABELS[m]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-1 gap-3">
        <Button className="flex-1" onClick={onExplain} disabled={disabled || busy !== null}>
          {busy === "explain" ? <Loader2 className="animate-spin" /> : <Search />}
          Explain My Error
        </Button>
        <Button
          className="flex-1"
          variant="secondary"
          onClick={onFix}
          disabled={disabled || busy !== null || !!fixDisabledReason}
          title={fixDisabledReason}
        >
          {busy === "fix" ? <Loader2 className="animate-spin" /> : <Wrench />}
          Fix My Code
        </Button>
      </div>
    </div>
  );
}
