# dgx-autoresearch — Journal

> Most-recent entry on top. Tracks what we adopted from where, why, and
> what we built ourselves. Companion to `README.md` (which describes
> what the repo IS) and `program.md` (which is the agent prompt).

---

## 2026-05-04 — Branch `antidote/blackwell-may4`: synthesis from upstream + community

**TLDR:** Forked karpathy/autoresearch as `LuisFX/dgx-autoresearch`.
Cherry-picked litesearch's GB10-applicable code (FA3→SDPA path, gradient
checkpointing, log_queue/stop_event IPC, compute_optimal_config, generate,
export_model, CLI flags). Added schaferk's overnight tooling under
`tooling/`. Patched `(12, 1): 213.0 TFLOPS` row into PEAK_FLOPS_TABLE
(GB10 / sm_121, sourced from schaferk's measured 16hr run). Authored
`program.md` with six failure-mode guards (G1-G6) + Goodhart caveat,
preserving Karpathy's loop discipline.

### What we adopted from where

| Source | What | Where it landed |
|---|---|---|
| karpathy/autoresearch master | base repo (all of it) | the fork itself |
| jlippp/litesearch main | `train.py` (FA3→SDPA, grad-ckpt, IPC primitives, compute_optimal_config, run_training/continue_training/generate/export_model, CLI) | root `train.py` |
| jlippp/litesearch main | `prepare.py` tweaks | root `prepare.py` |
| jlippp/litesearch main | `pyproject.toml` deps | root `pyproject.toml` (modified — see below) |
| schaferk/autoresearch-blackwell-gb10 main | `code/launch_agent.sh`, `code/monitor.py`, `code/analyze.py`, `code/experiment_journal.py`, `code/run_with_monitor.sh`, `code/backfill_data.py`, `code/BACKFILL_README.md` | `tooling/*` (unchanged from schaferk) |
| karpathy/autoresearch PR #547 | (10, 0)/(12, 0) BF16 FLOPS rows | `train.py` PEAK_FLOPS_TABLE |

### What we modified after adopting

- `pyproject.toml`:
  - `name`: litesearch → dgx-autoresearch
  - PyTorch index: `cu128` → `cu130` (Blackwell needs CUDA 13)
  - **dropped** `customtkinter` (litesearch's gui.py is desktop-only;
    we'll serve a web UI instead)
  - **added** `streamlit` (planned web UI)
- `train.py` PEAK_FLOPS_TABLE — added 4 rows:
  - `(10, 0) bf16: 2250` — datacenter Blackwell B100/B200 (from PR #547)
  - `(12, 0) bf16: 209`  — consumer Blackwell RTX 50xx (from PR #547)
  - **`(12, 1) bf16: 213`** — GB10 Grace Blackwell (DGX Spark) ← OURS,
    sourced from schaferk's measured 16-hour run
  - `(12, 1) fp32: 53` — GB10 fp32 estimate (4× bf16 ratio)
- `program.md` — written from scratch as a *superset* of upstream +
  litesearch's program.md, plus six new guards (G1-G6) and GB10-specific
  priors

### What we did NOT take

- **schaferk's repo restructure** (he moved everything to `code/`,
  dropped train.py/prepare.py/program.md from root) — too invasive and
  breaks compatibility with upstream's loop convention. We keep
  Karpathy's flat-root layout.
- **litesearch's `gui.py`** (CustomTkinter desktop GUI) — doesn't fit
  the headless DGX access pattern. Our web UI is Streamlit, served on
  port `:8088` over Tailscale.
- **litesearch's program.md verbatim** — we drafted ours with our own
  guards. Their content is preserved in our "Exporting" + "Agent
  workflow" sections at the end.

### The empirical baseline we should match or beat

schaferk's published 16-hour overnight run on actual GB10 hardware:

```
val_bpb:    1.463472  →  1.134565   (22.5% improvement)
params:     50.3M     →  22.5M      (model SHRANK)
steps/run:  ~93       →  ~1300      (steps grew 14×)
peak VRAM:  44 GB     →  6.1 GB     (used <5% of 128 GB UMA)
key insight:  "GB10 is step-limited, not VRAM-limited"
```

Their final config: `depth=4, dim=384, n_head=3, batch=2^16, MLP_expansion=7×`.
This is THEIR end state — our agent shouldn't blindly start there. But if
our agent's discoveries point back at this config, that's confirmation,
not coincidence.

### Branch shape

```
master (= karpathy/autoresearch master, 0 commits behind upstream)
  └── antidote/blackwell-may4   ← our cherry-picked + augmented base
        commits:
          d27fed8  pyproject.toml: cu128→cu130 + drop customtkinter + streamlit
          3f32c2f  train.py: add Blackwell rows to PEAK_FLOPS_TABLE
          [tooling commit hash]  schaferk tooling under tooling/
          fbb97a4  program.md: Antidote guards + GB10 priors
          [JOURNAL commit hash]  this file
        future runs branch from here as antidote/<tag>-<gpu>
```

### Remotes (for ongoing upstream-tracking)

```
origin       https://github.com/LuisFX/dgx-autoresearch.git    (our fork)
upstream     https://github.com/karpathy/autoresearch.git      (track main)
schaferk     https://github.com/schaferk/autoresearch-blackwell-gb10.git
lippp        https://github.com/jlippp/litesearch.git
```

To track upstream evolution: `git fetch upstream && git log master..upstream/master`.
When PR #547 lands, we can rebase our `antidote/*` branches on it.

### Sandbox (read-only references for ongoing extraction)

```
~/code/sandbox/autoresearch-blackwell-gb10/   (schaferk's full repo)
~/code/sandbox/litesearch/                    (lippp's full repo)
```

These are clones (not submodules — per Antidote convention "WE DON'T
SUBGIT"). Once we've extracted all useful content and the smoke run is
green, the sandbox dirs can be deleted; we live in the fork.

### What's still pending

- [ ] Web UI scaffold (Streamlit, `:8088`, hooks log_queue + stop_event)
- [ ] Sync scripts (push fork to DGX; pull results back)
- [ ] First DGX smoke run — verify train.py end-to-end on GB10
- [ ] Open follow-up upstream PR adding `(12, 1)` row to PR #547's MFU
      table once that lands
- [ ] After smoke green: launch `claude` in repo + watch overnight

### How this fits the broader Antidote stack

This fork is **research-side**, not directly on the SLM-vs-RAG critical
path. But the loop validates DGX Spark for sustained training workloads
(the parallel agent has been hitting M5 QLoRA-70B OOM; if a 16hr
nanoGPT loop runs cleanly on GB10, that's evidence M5 is recipe-specific
not Spark-fundamental). And whatever architecture/optimizer wins this
loop discovers may transfer to our SLM tuning later.

The `antidote/blackwell-may4` branch is the canonical handoff point —
all future research branches from here.
