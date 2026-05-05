# LuisFX fork README — `dgx-autoresearch`

> If you arrived here looking for upstream Karpathy autoresearch's project
> overview, you want [`README.md`](./README.md). **This document is for
> us** — the maintainers of this fork. It captures the operating model,
> sync hygiene, and current state.

---

## What this fork is

[karpathy/autoresearch](https://github.com/karpathy/autoresearch) adapted
for the **NVIDIA DGX Spark** — GB10 Grace Blackwell, sm_121, aarch64,
119 GiB UMA. The upstream project does not target this hardware. Two
community forks each cover *part* of the gap:

- [schaferk/autoresearch-blackwell-gb10](https://github.com/schaferk/autoresearch-blackwell-gb10)
  — measured GB10 FLOPS, FA3-not-supported finding, overnight tooling,
  16-hour reference run (1.463 → 1.135, 22.5% improvement)
- [jlippp/litesearch](https://github.com/jlippp/litesearch)
  — clean FA3→SDPA swap, gradient checkpointing, IPC primitives
  (`log_queue`, `stop_event`), `compute_optimal_config`,
  `generate`/`export_model`, CLI flags

We synthesize both *plus* additions of our own (the sm_121 row in the
FLOPS lookup table, six failure-mode guards in `program.md`, a Streamlit
web monitor, the Mac↔Spark sync workflow).

---

## How to maintain this fork (sync hygiene)

### Layout — what's upstream-touchable vs ours

```
dgx-autoresearch/
├── README.md                  ← UPSTREAM (don't modify; merge conflicts → painful)
├── README.LUISFX.md           ← OUR fork README (this file)
├── program.md                 ← OURS (agent prompt with Antidote guards)
├── train.py                   ← OURS (litesearch base + sm_121 patch)
├── prepare.py                 ← OURS (litesearch's tweaks adopted)
├── pyproject.toml             ← OURS (cu130 + streamlit; no customtkinter)
├── dashboard.py               ← OURS (Streamlit web monitor — new)
├── analysis.ipynb             ← UPSTREAM (preserve as-is)
├── progress.png               ← UPSTREAM (preserve as-is)
├── results/                   ← UPSTREAM (their published reference results)
├── tooling/                   ← from-schaferk (cherry-picked verbatim)
├── sync/                      ← OURS (push, pull, run, spark_setup wrappers)
└── journal/                   ← OURS (running narrative — see below)
```

### Branches we maintain

| Branch | Purpose |
|---|---|
| `master` | mirrors `upstream/master` exactly. Never edited. Used to catch upstream changes. |
| `antidote/blackwell-may4` | our cherry-picked + augmented base. All experiment branches start here. |
| `antidote/<tag>` | per-experiment branch claude operates on (e.g. `antidote/may4-gpu0`). Created from `antidote/blackwell-may4`. |

### Remotes

```
origin     https://github.com/LuisFX/dgx-autoresearch.git    (our fork)
upstream   https://github.com/karpathy/autoresearch.git      (track main)
schaferk   https://github.com/schaferk/autoresearch-blackwell-gb10.git
lippp      https://github.com/jlippp/litesearch.git
```

### Pulling upstream changes (the painless way)

Because we left `README.md` untouched, fetching upstream is nearly
conflict-free. The pattern:

```bash
git fetch upstream
git checkout master
git merge --ff-only upstream/master              # always fast-forwards
git push origin master                            # keep our fork's master honest

# now rebase our work on top
git checkout antidote/blackwell-may4
git rebase master
# resolve conflicts only on files WE modified (program.md, train.py,
# prepare.py, pyproject.toml). README.md stays clean → no conflict there.
```

If a rebase conflicts on `train.py`, that's expected — we and upstream
both edit it. Look at upstream's diff (`git log upstream/master ^master
-- train.py`) and decide whether to take their change (drop ours) or
keep ours (use `--ours` for that hunk).

### Bringing in new wisdom from sandbox repos

The sandbox clones at `~/code/sandbox/{autoresearch-blackwell-gb10,litesearch}`
are read-only references. To cherry-pick something new from them:

```bash
git fetch schaferk    # or git fetch lippp
git log master..schaferk/main --oneline -- <file>    # find what changed
git checkout schaferk/main -- <file>                  # surgical: just that file
# or: git cherry-pick <sha>                           # if attribution preserved
git diff --staged                                     # review carefully
git commit -m "from-schaferk <sha>: <what>"
```

Always **vet against GB10 first** — schaferk and lippp test on different
hardware (lippp on consumer GPUs, schaferk on the GB10 reference run).
A patch that works on RTX 3090 may not be optimal on sm_121. Smoke-test
before adopting.

### Our additions vs upstream/community (diff table)

| Concern | Upstream | Schaferk | Lippp | OURS |
|---|---|---|---|---|
| Attention | FA3 (Hopper) | SDPA on GB10 (claimed) | SDPA (consumer) | **SDPA (sm_121-validated)** |
| FLOPS lookup | hardcoded H100 | 213 TFLOPS for GB10 (no table) | per-cap table (no Blackwell) | **per-cap table + sm_121 row** |
| CUDA index | cu128 | (same as ours) | cu128 | **cu130** |
| `kernels` dep | required | not used | not used | **not used** |
| GUI | none | none | CustomTkinter | **Streamlit web @ :8088** |
| Tooling | none | full overnight kit | none | **schaferk's tooling/ verbatim** |
| program.md guards | basic loop | basic loop | basic loop | **G1-G6 + Goodhart** |
| Mac↔Spark | n/a | n/a | n/a | **sync/{push,pull,run,spark_setup}.sh** |

Every claim above is traceable in `git log` via the cherry-pick commit
messages (`from-lippp:`, `from-schaferk:`, `train.py: ... PEAK_FLOPS_TABLE
... from PR #547`, etc.).

---

## How to use this fork (operating model)

### Mac↔Spark contract — strict

> **Mac is git-authoritative for code AND history. Spark is a pure
> execution target.** Zero `.git` on the Spark. All commits, advances,
> resets happen on Mac.

| | **Mac** (`~/code/luisfx/dgx-autoresearch`) | **Spark** (`~/dgx-autoresearch`) |
|---|---|---|
| Code edits | ✅ canonical | ❌ rsync target only |
| Git history | ✅ full | ❌ no .git, no commits |
| Claude agent | ✅ runs the loop here | ❌ pure execution |
| `train.py` execution | ssh-fans-out via `sync/run.sh` | runs here when called |
| `run.log` | ✅ rsync'd back here | written here, then yanked |
| `results.tsv` | ✅ here (Mac runs the loop) | n/a |
| `exports/*.pth` | ✅ rsync'd back | written here, then yanked |
| Streamlit dashboard | view in browser | served at `:8088` over Tailscale |

### The 4 sync scripts

| Script | Direction | Purpose |
|---|---|---|
| `sync/push.sh` | Mac → Spark | rsync code only; **NEVER `git init`** there |
| `sync/spark_setup.sh` | one-shot remote | install uv + uv sync + prepare.py on Spark |
| `sync/run.sh` | inner loop | push + ssh-train + pull-back. The agent calls this. |
| `sync/pull.sh` | Spark → Mac | `latest` mode (in-place) for inner loop; default mode is timestamped audit snapshot in `audit/<UTC-timestamp>/` |

### One-time bring-up (Mac side)

```bash
cd ~/code/luisfx/dgx-autoresearch
git checkout antidote/blackwell-may4
bash sync/push.sh             # rsync code to Spark (~5 sec)
bash sync/spark_setup.sh      # one-time: uv + uv sync + prepare.py on Spark (~5 min)
bash sync/run.sh              # 5-min smoke train; run.log lands on Mac
grep -E "^(val_bpb|peak_vram_mb|GPU|Compute|Peak FLOPs):" run.log
```

Expected on GB10:
```
val_bpb:          ~1.46                      ← matches schaferk reference
peak_vram_mb:     ~6,000–45,000              ← depends on auto-config
GPU: NVIDIA GB10 ...
Compute capability: 12.1
Dtype: bfloat16
Peak FLOPs: 2.13e+14                          ← confirms our sm_121 row hit
```

### Each experiment thereafter (the loop, all Mac-side)

```bash
# 1. claude (or you) edits train.py
# 2. git commit on Mac
bash sync/run.sh                            # 5-min round-trip
grep "^val_bpb:" run.log
# decide keep/discard, advance or git reset on Mac, repeat
```

### Web monitor (when the run is hot)

```bash
# on Mac, separate terminal — runs the dashboard remotely on the Spark
ssh antidote@spark-28cb.tail462c57.ts.net \
  "cd ~/dgx-autoresearch && uv run streamlit run dashboard.py \
     --server.port 8088 --server.address 0.0.0.0 --server.headless true"

# on Mac browser
open http://spark-28cb.tail462c57.ts.net:8088
```

### Audit trail at end of an overnight run

```bash
bash sync/pull.sh             # snapshots run.log + exports/ to audit/<ts>/
git log antidote/<tag>        # claude's intra-loop commit history (Mac-side)
cat results.tsv               # agent's keep/discard scoreboard
ls audit/                     # all overnight snapshots, dated
```

---

## Reference baselines

| Run | val_bpb start | val_bpb end | Wallclock | Source |
|---|---|---|---|---|
| schaferk overnight #1 | 1.463 | 1.135 (22.5% better) | 16 hr (151 experiments) | [their repo](https://github.com/schaferk/autoresearch-blackwell-gb10) |
| `antidote/blackwell-may4` baseline smoke | TBD | (n/a) | ~7 min (sync + train + sync) | (planned) |
| `antidote/may4-gpu0` first overnight | TBD | TBD | TBD | (planned) |

---

## Pointers

| File | Purpose |
|---|---|
| [`README.md`](./README.md) | Upstream Karpathy README — preserved as-is; do not edit |
| [`README.LUISFX.md`](./README.LUISFX.md) | This file — fork operating model + sync hygiene |
| [`program.md`](./program.md) | Agent prompt with G1–G6 guards + GB10 priors |
| [`train.py`](./train.py) | What the agent edits during the loop |
| [`prepare.py`](./prepare.py) | Fixed: data + tokenizer + evaluation; do not modify |
| [`dashboard.py`](./dashboard.py) | Streamlit web monitor (run on Spark, view from Mac) |
| [`pyproject.toml`](./pyproject.toml) | uv deps; cu130 index, Blackwell-aware |
| [`tooling/`](./tooling/) | schaferk's overnight tooling (Spark-shaped; needs adaptation for Mac-driven) |
| [`sync/`](./sync/) | Mac↔Spark scripts (push, pull, run, spark_setup) |
| [`journal/`](./journal/) | Running narrative — `journal/{datetime}-{concept}.md` |
| [`results/`](./results/) | Upstream's published reference results (preserved) |
| [`analysis.ipynb`](./analysis.ipynb) | Upstream's analysis notebook |

---

## Acknowledgments

- [Andrej Karpathy](https://github.com/karpathy/autoresearch) — original
  autoresearch design + the loop pattern
- [schaferk](https://github.com/schaferk/autoresearch-blackwell-gb10) —
  measured GB10 FLOPS, FA3-not-supported finding, overnight tooling,
  16-hr reference run
- [jlippp](https://github.com/jlippp/litesearch) — clean FA3→SDPA swap,
  gradient checkpointing, IPC primitives, compute_optimal_config,
  generate/export_model, CLI flags
- [lonexreb](https://github.com/karpathy/autoresearch/pull/547) — PR #547
  introducing the per-compute-cap FLOPS lookup pattern; we added the
  sm_121 row

License: inherits Apache-2.0 from upstream `karpathy/autoresearch`.
