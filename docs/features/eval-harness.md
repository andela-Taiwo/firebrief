# eval-harness: turn "it seems to work" into a number

**Status:** In progress · **Branch:** `feat/eval-harness`
**Depends on:** `answer-pipeline` · **Unblocks:** the README's results table

## Goal

A reproducible run over a labelled question set that reports answer accuracy, citation
precision, refusal accuracy and cost — so a prompt, model, chunking or retrieval change is
a measured delta rather than an opinion, and so a regression fails CI.

## Scope

**In**
- A labelled case set: question, whether it should be answered or refused, the section
  that should answer it, and the terms the answer must contain.
- A runner that executes the real pipeline and scores each case.
- Metrics: answer accuracy, refusal accuracy, citation precision, p95 latency, total cost.
- An **extractive baseline provider**: quotes the first sentence of the top source. It is
  the bar a real model has to beat, and it runs with no API key.
- `make eval` printing a table, exiting non-zero below a threshold.

**Out (and where it goes)**
- A real corpus and 100+ questions: this harness is built against the checked-in fixture
  corpus, so today it proves the plumbing and the metrics. The question set grows with the
  corpus.
- Live provider runs in CI: they cost money and are non-deterministic. The script supports
  them; CI runs the baseline.

## Decisions & trade-offs

### D1. Baseline before benchmark
An extractive provider gives a floor. A model that scores below it is not adding value, and
that comparison is the first table worth publishing.

### D2. Correctness is terms present, not a judge
Grading answers with a model makes the metric non-deterministic and expensive. Each case
lists the terms a correct answer must contain, which is crude but reproducible; the
citation verifier already proves the quotes are real.

### D3. The set is checked in and small
A dozen cases over three sections is not a quality claim. It is the shape of the harness,
and the docstring says so.

## Acceptance criteria

1. Running the suite against the baseline provider produces a report with per-case outcomes.
2. An answer that misses a required term is scored incorrect.
3. A case expected to be refused but answered is scored incorrect, and vice versa.
4. Citation precision is verified checks over all checks.
5. The summary reports accuracy, refusal accuracy, citation precision, cost and p95 latency.
6. `make eval` exits non-zero when accuracy is below the threshold.
7. The run is deterministic: the same inputs give the same report.

## Test plan

Runner logic is tested with scripted providers, not the real pipeline's luck: a correct
answer, a missing term, a wrong refusal, a wrong answer. The baseline provider is tested on
a prompt it did not write.

Canaries: stop counting missing terms; count a refusal as an answer; make citation
precision always 1.0.

## Risks

| Risk | Mitigation |
|---|---|
| A tiny set flatters the system | Said plainly in the docstring and the summary line |
| Terms are a crude proxy for correctness | The citation verifier covers the part that matters most: the quote is real |
| Cost omitted without a price table | Cost is reported as 0 and labelled "unpriced" when no table is supplied |

## Effort

2 dev-days, one PR.

## Build notes

### First measured baseline

```
case                     expect  got                  cites  ok
dead-ends                answer  answered             1.00   yes
doors-self-closing       answer  answered             1.00   yes
doors-rating             answer  answered             1.00   yes
detection-standard       answer  answered             1.00   yes
no-answer-colour         refuse  answered             1.00   NO
no-answer-cost           refuse  answered             1.00   NO

accuracy 0.67 (4/6) · answers 1.00 · refusals 0.00 · citation precision 1.00
```

That is the extractive baseline doing exactly what it should: it quotes the top source
perfectly, cites it correctly, and cannot refuse, so it fails both refusal cases. A real
model has to beat 0.67 by declining when the corpus does not answer — which is the first
comparison worth publishing.

### What this run does and does not prove

It proves the harness works end to end: ingestion, embedding, retrieval, the pipeline, the
verifier and the metrics. It does **not** prove answer quality: six cases over three
sections, with a bag-of-words embedder and a provider that never refuses. Said plainly in
the module docstring and here.

### Canaries

| # | Break | Caught by |
|---|---|---|
| C55 | Required terms ignored | missing-term test |
| C56 | A refusal counts as an answer | refusal-where-answer-expected test |
| C57 | Citation precision hardcoded to 1.0 | precision test |
