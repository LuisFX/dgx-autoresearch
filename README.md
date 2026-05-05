# dgx-autoresearch

> Antidote's fork of [karpathy/autoresearch](https://github.com/karpathy/autoresearch),
> tuned for the **NVIDIA DGX Spark (GB10 Grace Blackwell, sm_121, aarch64,
> 119 GiB UMA)**. Synthesized with adaptations from
> [schaferk/autoresearch-blackwell-gb10](https://github.com/schaferk/autoresearch-blackwell-gb10)
> and [jlippp/litesearch](https://github.com/jlippp/litesearch).

![teaser from upstream](progress.png)

---

## What this is

Karpathy's autoresearch — an AI agent overnight loop that mutates a
single-GPU `train.py`, trains for 5 minutes, scores `val_bpb`, keeps
wins, discards losses. Original idea: ~12 experiments per hour, ~100
overnight, stable improvements as the agent finds GPU-specific wins.

This fork makes it work on the **DGX Spark** (which is *not* a stock
NVIDIA GPU profile — it's GB10, sm_121, 119 GiB UMA, aarch64). The
adaptations are all small surgical patches; we didn't rewrite anything.

For the full provenance — what was cherry-picked from where and why —
see [`JOURNAL.md`](./JOURNAL.md).

## How this differs from upstream

| Concern | Upstream | This fork |
|---|---|---|
| Attention | FlashAttention-3 (CUDA-only kernels) | PyTorch SDPA (~2% faster on GB10 per community benchmarks) |
| FLOPS lookup for MFU | hard-coded H100 (989.5 TFLOPS) | per-compute-cap table inc. **sm_121: 213 TFLOPS** |
| CUDA index | cu128 | cu130 |
| `kernels` package | required | dropped |
| GUI | (none) | Streamlit web UI on `:8088`, Tailscale-accessible (planned) |
| Tooling | (basic) | schaferk's overnight tooling under `tooling/` |
| Failure-mode guards in program.md | (basic loop discipline) | six numbered guards + Goodhart (G1-G6) |

## Layout

```
dgx-autoresearch/
├── README.md          this file
├── JOURNAL.md         what we cherry-picked from where, why
├── program.md         the agent prompt (Karpathy + Antidote guards)
├── train.py           the file the agent edits — model + optimizer + loop
├── prepare.py         fixed: data prep + tokenizer + evaluation (don't edit)
├── pyproject.toml     uv deps; cu130 index for Blackwell
├── analysis.ipynb     upstream's analysis notebook
├── results/           upstream's published reference results (don't edit)
└── tooling/           schaferk's overnight tooling (launch_agent.sh,
                       monitor.py, analyze.py, experiment_journal.py, ...)
```

## Quick start (DGX Spark)

```bash
# 1. uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. clone
cd ~ && git clone https://github.com/LuisFX/dgx-autoresearch.git
cd dgx-autoresearch
git checkout antidote/blackwell-may4

# 3. deps + data prep
uv sync
uv run prepare.py

# 4. baseline smoke run (5 min)
uv run train.py

# expected on GB10:
#   val_bpb ≈ 1.463 (matches schaferk reference baseline)
#   peak_vram_mb ≈ 6,000–45,000 (depends on auto-config decisions)
#   training_seconds ≈ 300

# 5. launch the agent
claude
# at the prompt:
# > Read program.md and JOURNAL.md, then kick off a new experiment
# >   with the antidote/may4-gpu0 branch tag.
```

## Reference baselines

| Run | val_bpb start | val_bpb end | Wallclock | Source |
|---|---|---|---|---|
| schaferk overnight #1 | 1.463 | 1.135 (22.5% better) | 16 hr (151 experiments) | [schaferk repo](https://github.com/schaferk/autoresearch-blackwell-gb10) |
| our antidote/blackwell-may4 #1 | TBD | TBD | TBD | (planned) |

## Live monitor (planned)

While running on DGX, the Streamlit web dashboard will be at:

`http://spark-28cb.tail462c57.ts.net:8088`

Features (mirrors litesearch's gui.py concepts but web-native, no X11):
- Live training-log tail (auto-scroll)
- val_bpb over time chart
- VRAM usage bar + GPU temp/power
- results.tsv viewer (sortable, with win/loss badges)
- "Try it" generate popup (calls `generate()` from train.py)
- Config-slider hint generator (writes hint lines for program.md)
- Start/Stop/Pause buttons (signals via `stop_event`)
- Audit-capsule list per win
- Git-diff viewer (what the agent changed since last keep)

## Acknowledgments

- **[Andrej Karpathy](https://github.com/karpathy/autoresearch)** — the
  original autoresearch design + the loop pattern
- **[schaferk](https://github.com/schaferk/autoresearch-blackwell-gb10)**
  — measured GB10 FLOPS, FA3-not-supported finding, overnight tooling,
  16-hour reference run
- **[jlippp](https://github.com/jlippp/litesearch)** — clean FA3→SDPA
  swap, gradient checkpointing, IPC primitives (log_queue, stop_event),
  compute_optimal_config, generate/export_model, CLI flags
- **[lonexreb](https://github.com/karpathy/autoresearch/pull/547)** —
  PR #547 introducing the per-compute-cap FLOPS lookup pattern; we
  added the sm_121 row

## License

Inherits Apache-2.0 from upstream karpathy/autoresearch.
