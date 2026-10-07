# Evaluation

## 1. What is measured

`backend/evaluate.py` runs the agent against the bug fixtures and reports five metrics:

| Metric | Definition |
|---|---|
| **Error identification accuracy** | The `error_type` returned in explain mode matches one of the fixture's accepted names. |
| **First-attempt fix success rate** | Attempt 1 exited 0 **and** (when an expected output is defined) printed exactly that. |
| **Overall fix success rate** | A verified fix was produced within the attempt budget. |
| **Average attempts per successful fix** | Mean attempt count over the successful cases only. |
| **Explanation completeness** | Structural score: are all five parts present and non-trivial (error type, summary ≥ 15 chars, explanation ≥ 60 chars, concept, problematic lines). |

A sixth, `why_it_worked_completeness`, applies the same structural check to the "Why Did My Fix
Work?" output.

**Completeness is structural, not semantic.** It answers "did the agent fill in every required
part?", not "is the explanation correct or well written?". Judging correctness needs a human or a
grader model; that is listed under future work rather than quietly approximated.

## 2. How a case is scored

Nothing is hard-coded. For each fixture the harness:

1. **Runs the buggy code in the sandbox** to obtain the real error text — the traceback, the
   timeout notice, or a "wrong output: expected X, actual Y" description for bugs that do not
   crash. A fixture that does not actually misbehave raises an error instead of being scored.
2. **Calls `mode=explain`** and compares the predicted error type with the accepted names.
3. **Calls `mode=fix`** and records whether the final fix was verified, and how many attempts it
   took.

Verification is the sandbox's verdict (exit code, plus an exact stdout comparison where an
expected output is defined), so a model cannot pass by claiming success.

## 3. The test set

18 fixtures in `backend/tests/fixtures/bugs.json`, covering every category the brief asks for:

| # | Fixture | Category | Failure mode |
|---|---|---|---|
| 1 | `index_error_basic` | IndexError | exception |
| 2 | `type_error_concat` | TypeError | exception |
| 3 | `key_error_typo` | KeyError | exception |
| 4 | `name_error_typo` | NameError | exception |
| 5 | `value_error_int` | ValueError | exception |
| 6 | `attribute_error_list` | AttributeError | exception |
| 7 | `zero_division_counter` | ZeroDivisionError | exception |
| 8 | `syntax_error_colon` | SyntaxError | exception |
| 9 | `off_by_one_slice` | Off-by-one | wrong output |
| 10 | `wrong_conditional_adult` | Wrong conditional | wrong output |
| 11 | `infinite_loop_no_increment` | Infinite loop | timeout |
| 12 | `list_mutation_while_iterating` | Incorrect list mutation | wrong output |
| 13 | `missing_return` | Missing return | exception |
| 14 | `dict_nested_access` | Incorrect dictionary access | exception |
| 15 | `wrong_function_args` | Wrong function arguments | exception |
| 16 | `unbound_local` | UnboundLocalError | exception |
| 17 | `import_error_name` | ImportError | exception |
| 18 | `chained_two_bugs` | Chained bugs | exception, then a second exception |

Each fixture carries its code, expected output, and a reference fix. Every one is checked by the
test suite: the buggy code must really fail, and the reference fix must really produce the
expected output. `chained_two_bugs` also carries a `naive_fix` — the plausible first attempt that
still fails — which is what drives the retry demo.

## 4. Running it

```bash
cd backend
source .venv/bin/activate
python evaluate.py                                   # all 18 fixtures
python evaluate.py --ids index_error_basic,chained_two_bugs
python evaluate.py --limit 5 --style interview
python evaluate.py --out runs/gpt4o-mini.json
```

It needs a real `OPENAI_API_KEY`; without one it refuses to run rather than printing numbers from
a stub. Each case makes two agent runs (explain + fix) and several sandboxed executions, so the
full set takes a few minutes and costs real tokens.

Output: a table on stdout, plus `evaluation_results.json` (per-case rows) and
`evaluation_results.md` (the table), both stamped with the model, style, attempt limit and
timestamp.

## 5. Results

**No numbers are published here.** The results depend entirely on which model you configure, and
inventing them would defeat the point of the exercise. Run the command above with your own key
and paste the generated table into this section:

```markdown
| Metric | Result |
|---|---|
| Error identification accuracy | ... |
| First-attempt fix success rate | ... |
| Overall fix success rate | ... |
| Average attempts per successful fix | ... |
| Explanation completeness (structural) | ... |
```

For a presentation, run it once per model (for example `gpt-4o-mini` vs `gpt-4o`) with
`--out` pointing at different files; the per-category breakdown in the JSON shows which bug types
a model handles poorly.

## 6. What the automated tests cover instead

The 91-test suite (`pytest`) runs with no API key and no cost, because the LLM is replaced by a
**scripted** stand-in (`tests/fake_llm.py`) that returns fixed tool calls and canned JSON. It
verifies the system's logic rather than a model's intelligence:

- the sandbox (timeout, output flood, no network, no secrets, clean tracebacks, exit codes);
- the analyzer against every exception fixture;
- the agent loop: retry after a failure, the attempt budget, sandbox-over-model ground truth;
- every guard rail and failure path in the table in `agent-workflow.md`;
- the HTTP contract and the SSE event order;
- the evaluation arithmetic itself (`test_evaluate.py`), using cases whose outcome is known by
  construction.

So: `pytest` answers "is the machinery correct?", `evaluate.py` answers "how good is this model at
debugging?". Keep the two claims separate when presenting.
