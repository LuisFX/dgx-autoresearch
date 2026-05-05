# 2026-05-05T0000 — Sync-script synthesis: best-of-both-worlds with the dgx repo

> Companion to [`../sync/README.md`](../sync/README.md) (the cross-repo
> convention v1).

## Headline

The dgx repo's `scripts/sync-*.sh` family had been proven over weeks of
B2/B3/K3 workloads on the spark. Our autoresearch `sync/*.sh` were
freshly authored, untested, missing several patterns the dgx repo had
already paid for. Synthesized — our scripts now incorporate the proven
patterns; the convention is documented in `sync/README.md` so the dgx
repo can converge to the same shape next iteration.

## What we ran

```bash
diff <(cat ../dgx/.../scripts/sync-to-spark.sh)  sync/push.sh
diff <(cat ../dgx/.../scripts/sync-audit-back.sh) sync/pull.sh
# read ship-parallel.sh, sync-corpus-back.sh
# extracted the patterns
```

## What we adopted from the dgx repo

| Pattern | Source script | Where it lands here |
|---|---|---|
| UTC ISO timestamps in log lines | sync-to-spark, sync-audit-back, ship-parallel | All 4 of our scripts |
| Compact UTC dir timestamps `YYYYmmddTHHMMSSZ` | sync-corpus-back | sync/pull.sh (audit-snapshot mode) |
| `BASH_SOURCE` path derivation | sync-corpus-back | sync/run.sh (was relative-to-CWD before) |
| Secret excludes (`.env*`, `*.env`, `.gitignore`) | sync-to-spark | sync/push.sh |
| Binary checkpoint excludes (`*.bin`, `*.safetensors`) | sync-audit-back | sync/pull.sh |
| Empty-result cleanup (rmdir + non-zero exit) | sync-corpus-back | sync/pull.sh |
| Preflight checks (uv, nvidia-smi, tmux, disk) | ship-parallel | sync/spark_setup.sh |
| Monitoring hints printed at end | ship-parallel | sync/spark_setup.sh, sync/run.sh |
| tmux integration for long-running | ship-parallel | sync/run.sh `--tmux` flag |
| `## comment-block` header style with SCOPE + Excludes | all dgx scripts | All 4 of our scripts |

## What we keep (not yet in the dgx repo)

These would benefit dgx scripts too — recommendation for next iteration there:

| Pattern | Why valuable |
|---|---|
| `SPARK_HOST` / `REMOTE_DIR` env-var overrides with defaults | Testing against staging, alternate paths |
| `mkdir -p` remote dir on first push | First-touch ergonomics |
| Pass-through args via `--` separator | Trivial extra flags (e.g. `--export`) |
| `--no-pull` mode | Leave artifacts on DGX for diagnosis without re-syncing |

## The cross-repo "in-sync" model

The user's directive: "in sync from now on." Without submodules
("WE DON'T SUBGIT"), the discipline is **manual convention**:

1. **`sync/README.md`** in this repo is the canonical doc of v1 conventions.
2. When **either** repo's sync scripts change, the **convention doc** updates
   alongside (bumped to v2 + migration note).
3. The other repo follows when it next iterates — either we update the dgx
   repo's scripts ourselves at that time, or we file an issue/note for the
   parallel agent to pick up.
4. We do **NOT** unilaterally modify the parallel agent's scripts mid-run
   (that's a merge-conflict risk). We **leave a breadcrumb** that points
   at our convention.

## The breadcrumb (this commit)

A single-line pointer added to the dgx repo's
`plans.documented/2026-05-03-fhir-qa-mvp/scripts/README.md` (or a fresh
`SYNC_CONVENTION.md` if no README exists), referencing
`/Users/luisfx/code/luisfx/dgx-autoresearch/sync/README.md`.

The parallel agent finds it when they next look at scripts/, can review
the convention, and decides whether to adopt the additions on their
side. Soft sync, no surprise edits.

## Lessons recorded for permanence

1. **Adopt before authoring.** When community + parallel-agent code
   already exists for the same problem, scan it FIRST before writing
   new code. Saves re-discovering patterns.
2. **The `## ` comment-block header style with SCOPE + Excludes is high
   ROI** — anyone reading the script in 6 weeks can tell what's in/out
   without reading the rsync flags.
3. **Convention v1 → v2 migration discipline** is the cost of the
   no-submodule choice. We accept that cost for the simplicity dividend.

## What's next (no behavior change yet)

These changes are pure refactors of our 4 scripts + a new convention doc.
No verification needed beyond "they still work" — which we'll test
when we run the smoke (next operator action: `bash sync/push.sh`).
