# dgx-autoresearch — agent program

This is Antidote's fork of Karpathy's autoresearch, tuned for the
NVIDIA DGX Spark (GB10 Grace Blackwell, sm_121, aarch64). The agent runs
overnight, mutating `train.py`, scoring `val_bpb`, keeping wins, discarding
losses.

> **You are running on a DGX Spark.** That's NVIDIA GB10 Grace Blackwell,
> compute capability sm_121, 119 GiB Unified Memory Architecture, aarch64.
> CUDA 13.0 in container. FlashAttention-3 is NOT used here (community
> finding: PyTorch SDPA is ~2% faster on GB10). FA3 references in any
> code suggest you've copied something old — replace with SDPA.

---

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `may4`).
   The branch `antidote/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b antidote/<tag>` from current
   `antidote/blackwell-may4` (the cherry-picked base).
3. **Read the in-scope files**: The repo is small. Read these for full context:
   - `README.md` — repository context.
   - `JOURNAL.md` — what we cherry-picked from where, why.
   - `prepare.py` — fixed constants, data prep, tokenizer, dataloader, evaluation. Do not modify.
   - `train.py` — the file you modify. Model architecture, optimizer, training loop.
4. **Verify data exists**: Check that `~/.cache/autoresearch/` contains data
   shards and a tokenizer. If not: `uv run prepare.py`.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row.
   The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs on a single GPU. The training script runs for a
**fixed time budget of 5 minutes** (wall clock training time, excluding
startup/compilation). Launch: `uv run train.py`.

**What you CAN do:**
- Modify `train.py` — this is the only file you edit. Everything is fair
  game: model architecture, optimizer, hyperparameters, training loop,
  batch size, model size, etc.

**What you CANNOT do:**
- Modify `prepare.py`. Read-only. Contains the fixed evaluation, data
  loading, tokenizer, and training constants (time budget, sequence
  length, etc).
- Install new packages or add dependencies. You can only use what's
  already in `pyproject.toml`.
- Modify the evaluation harness. The `evaluate_bpb` function in
  `prepare.py` is the ground truth metric.

**The goal is simple: get the lowest val_bpb.** The 5-minute budget is
fixed — every experiment is directly comparable. Architecture, optimizer,
hyperparameters, batch size, model size — all fair game. Only constraint:
runs without crashing, finishes in budget.

**VRAM** is a soft constraint. **GB10 has 119 GiB of UMA — you have
huge headroom.** The schaferk benchmark's 16hr run on GB10 used only
6.1 GB, so memory is rarely the binding constraint. The binding
constraint on GB10 is **steps per 5-minute budget** (schaferk's
empirical finding: "GB10 is step-limited, not VRAM-limited"). More
training steps tend to beat bigger models. Use this as a prior.

**Simplicity criterion**: All else equal, simpler is better. A small
improvement that adds ugly complexity is not worth it. A small
improvement from *deleting* code is great — that's a simplification win.
A 0.001 val_bpb gain that adds 20 lines of hacky code? Probably not worth it.
A 0.001 gain from removing code? Definitely keep. An improvement of ~0
but cleaner code? Keep.

**The first run**: Always establish the baseline first — run the script as is.

## Output format

Once the script finishes it prints a summary like this:

```
---
val_bpb:          0.997900
training_seconds: 300.1
total_seconds:    325.9
peak_vram_mb:     45060.2
mfu_percent:      39.80
total_tokens_M:   499.6
num_steps:        953
num_params_M:     50.3
depth:            8
```

Extract the key metric:
```
grep "^val_bpb:" run.log
```

## Logging results

Append to `results.tsv` (tab-separated; commas break in descriptions).

The TSV header:
```
commit	val_bpb	memory_gb	status	description
```

1. git commit hash (short, 7 chars)
2. val_bpb achieved (e.g. 1.234567); use 0.000000 for crashes
3. peak memory in GB, .1f (e.g. 12.3 — `peak_vram_mb / 1024`); 0.0 for crashes
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried

Example:
```
commit	val_bpb	memory_gb	status	description
a1b2c3d	1.463472	44.0	keep	baseline (schaferk reference: 1.463 on GB10)
b2c3d4e	1.456000	44.2	keep	increase MATRIX_LR to 0.06
c3d4e5f	1.470000	44.0	discard	switch to GeLU activation
d4e5f6g	0.000000	0.0	crash	double model width (NaN loss)
```

`results.tsv` is **untracked** — leave it out of git. Use commit hash to
correlate runs to code.

## The experiment loop

Runs on a dedicated branch (e.g. `antidote/may4-gpu0`).

LOOP FOREVER:

1. Look at git state: current branch/commit
2. Tune `train.py` with an experimental idea — direct code edits
3. `git commit`
4. `uv run train.py > run.log 2>&1` (redirect everything; do NOT use tee
   or let output flood your context)
5. `grep "^val_bpb:\|^peak_vram_mb:" run.log`
6. If empty, the run crashed: `tail -n 50 run.log` for stack trace.
   If it's a typo/import bug, fix and re-run. If the idea is broken,
   log "crash" and move on.
7. Record results in `results.tsv` (do NOT commit the tsv)
8. If val_bpb improved (lower), advance the branch — keep the commit
9. If val_bpb is equal or worse, `git reset` back

You're a completely autonomous researcher. Try things. If they work, keep.
If they don't, discard. Advance the branch to iterate. Rewind sparingly.

**Timeout**: ~5 min total per experiment + a few seconds startup/eval.
If a run exceeds 10 minutes, kill and treat as discard.

**Crashes**: dumb-and-easy → fix and re-run. Fundamentally broken idea
→ log "crash" and skip.

**NEVER STOP**: Once the loop has begun, do NOT pause to ask. The human
is asleep or absent and expects you to work indefinitely until manually
stopped. If you run out of ideas, think harder — re-read the code,
consider radical changes, combine previous near-misses, look at recent
papers referenced in train.py docstrings.

Approx 12 experiments/hour, ~100 over an average human sleep.

---

## Antidote guards (six failure modes + Goodhart)

These are the disciplined-research guardrails for this loop. They come
from the "Why LLMs Aren't Scientists Yet" paper as cited by myoid.com's
autoresearch analysis, plus our own SLM-vs-RAG experiment design.

### G1 — Don't bias toward training-data defaults

Common-default architectures aren't necessarily right for GB10 sm_121.
**Try novel directions that aren't well-represented in your training
data.** Combinations of recent work, ablations of standard components,
unconventional optimizer hybrids — these are where untapped wins live.

### G2 — Don't drift under execution pressure

When a run takes longer than expected or eval is delayed, the temptation
is to skip steps (skip eval, skip git commit, skip writing the result
to TSV). **Don't.** Every experiment must complete the full loop or be
discarded as a crash. Partial results corrupt the scoreboard.

### G3 — Re-read program.md every ~10 experiments

Long-horizon memory degradation is a known failure mode. **Every 10
experiments, re-read this file in full.** Re-anchor on the goal, the
guards, and the schaferk reference baseline (1.463). If you find
yourself drifting from the loop shape, that's the signal.

### G4 — Never declare success without verifying val_bpb actually improved

Numerical bugs, eval skipping, NaN handling can all *look* like wins.
**Always** read `val_bpb:` directly from the run log via grep before
"keeping" a change. If val_bpb is `0.000000`, that's a crash, not a 100%
improvement. If val_bpb is `nan`, that's broken, not a win.

### G5 — Pivot deliberately when one direction exhausts

When 3+ experiments in a direction show no improvement, **pivot
deliberately to a categorically different direction** — not random
mutations. Random changes after exhaustion is the agent-disorientation
signal. Examples of deliberate pivots:
- Architecture ablation tried out → switch to optimizer changes
- Optimizer hyperparams done → try LR schedule shape
- LR done → try a different attention pattern (within SDPA's API)
- Attention done → try different normalization (RMS-norm variants)

### G6 — Goodhart on val_bpb

Optimizing val_bpb alone may degrade unmeasured properties (training
stability, generation quality, robustness to short prompts). **Once an
experiment is logged as a "keep," run a quick `generate()` sanity check
with a short prompt and a known prompt — if the output is gibberish or
repetitive while val_bpb improved, flag it in the description (e.g.
`status=keep, description="LR=0.06 — val_bpb=1.40, but generate('The')
loops 'the the the'"`).** Don't auto-discard, but the human reviewing
the scoreboard should see the smell.

### Reference baseline

The schaferk repo ran this loop overnight on GB10 and went **1.463 →
1.135 (22.5% improvement)** over 16 hours, 151 experiments. That's the
floor we should match or beat. Their final config:

  depth=4, dim=384, n_head=3, batch=2^16, MLP_expansion=7×, ~1300 steps/run

Don't blindly start there — that's THEIR end state. Start from our
baseline and let the loop discover. But if your discoveries point you
back at depth=4 / dim=384 / batch=2^16, that's confirmation, not coincidence.

---

## Exporting models

After training, export weights + config:

```bash
# Train and export
uv run train.py --export model.pth

# Train and export to a directory (auto-named by timestamp)
uv run train.py --export-dir exports/
```

Export contents:
- `state_dict` — model weights
- `config` — model architecture (depth, n_embd, heads, vocab_size, etc.)
- `use_bf16` — whether bfloat16 is in use

Loading:
```python
import torch
from train import GPT, GPTConfig
data = torch.load('model.pth', weights_only=False)
config = GPTConfig(**data['config'])
model = GPT(config); model.load_state_dict(data['state_dict'])
```

## Web monitor (planned)

A Streamlit dashboard will be served at `:8088` on the Spark, accessible
via Tailscale at `http://spark-28cb.tail462c57.ts.net:8088`. It hooks the
`log_queue` + `stop_event` IPC primitives litesearch designed into
`run_training()`. **Until that lands, monitor via `tail -f run.log` and
`watch -n 1 'cat results.tsv | tail'`.**

## Agent workflow (autopilot)

```bash
# Run 10 experiments
for i in $(seq 1 10); do
    uv run train.py --export-dir exports/ >> run.log 2>&1
    val_bpb=$(grep "^val_bpb:" run.log | tail -1 | awk '{print $2}')
    echo "Run $i: val_bpb=$val_bpb"
done
```

Or use `tooling/launch_agent.sh` (cherry-picked from schaferk) for a
schaferk-shaped overnight run.
