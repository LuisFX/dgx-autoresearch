# sync/ — Mac↔Spark scripts (cross-repo convention)

> The patterns here are **shared by convention** with `~/code/luisfx/dgx`'s
> `plans.documented/<plan>/scripts/sync-*.sh` family. We don't subgit; we
> just keep the conventions in lockstep across both repos.

## Why a convention, not a shared library

We have two repos that both drive the DGX Spark:

| Repo | Drives | Sync scripts |
|---|---|---|
| `~/code/luisfx/dgx` | NeMo fine-tune, Synthea, qa_bakeoff, FHIR-Q/A | `plans.documented/<plan>/scripts/{sync-to-spark,sync-audit-back,sync-corpus-back,ship-parallel}.sh` |
| `~/code/luisfx/dgx-autoresearch` | autoresearch overnight loop | `sync/{push,pull,run,spark_setup}.sh` |

The patterns rhyme but the specifics differ. Rather than introduce a shared
git submodule (rejected per "we don't subgit") or a third "spark-utils" repo,
we keep **identical conventions** across the two repos. When the parallel
agent next iterates on dgx repo's scripts, they should adopt the patterns
documented here. When we iterate ours, we should source-of-truth from the
dgx repo's proven patterns.

## Convention v1 (this commit)

### Logging — UTC ISO timestamps

Every script logs a one-line header at start with UTC ISO timestamp:

```bash
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[push→spark] $TS — $LOCAL_DIR  →  $SPARK:$REMOTE_DIR"
```

For audit dirs we use the compact filename-safe form:
```bash
TS_DIR="$(date -u +%Y%m%dT%H%M%SZ)"   # 20260505T123045Z
```

Both forms sort lexicographically; the long form is human-readable, the
short form is filename-safe.

### Path derivation — robust to CWD

Every script derives its anchor paths from `BASH_SOURCE`, not relative
to CWD:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
```

This means `bash sync/push.sh` works the same as
`bash /full/path/to/sync/push.sh` regardless of the caller's CWD.

### Env-var overrides

Always allow `SPARK_HOST` and the relevant remote dir to be overridden via
environment, with sensible defaults:

```bash
SPARK="${SPARK_HOST:-antidote@spark-28cb.tail462c57.ts.net}"
REMOTE_DIR="${REMOTE_DIR:-/home/antidote/dgx-autoresearch}"
```

Useful for testing against staging hosts, alternate paths, etc.

### Excludes — secrets & junk by default

Every push script excludes:
- `.git/` and `.gitignore` (DGX is execution target, not git source)
- `.venv/`, `__pycache__/`, `*.pyc` (regenerable)
- `.DS_Store` (macOS junk)
- `.env`, `.env.*`, `*.env` (secrets stay on Mac — defense-in-depth)
- Repo-specific generated artifacts (audit/, run.log, results.tsv, etc.)

Every pull script for binary-emitting work excludes:
- `*.bin`, `*.safetensors`, `*.pt` (large model weights)

### Subtree-only filter pattern

When pulling specific subtrees (`audit/` from any depth, etc.), use
rsync's filter trick:

```bash
rsync -avzm \
  --include='*/' \
  --include='audit/***' \
  --exclude='*' \
  "$SPARK:$REMOTE/" "$LOCAL/"
```

`-m` / `--prune-empty-dirs` removes empty plan dirs that didn't have
the subtree.

### Idempotency

`spark_setup.sh` and `push.sh` are designed to be safe to re-run:
- `mkdir -p` for any directory creation
- `command -v uv >/dev/null && ...` before installing
- `uv sync` no-ops if already synced
- `prepare.py` no-ops if data already cached

### Empty-result cleanup

Pull scripts that may match nothing should clean up empty audit dirs and
exit non-zero so callers can detect:

```bash
PULLED="$(find "$AUDIT_DIR" -type f | wc -l | tr -d ' ')"
if [ "$PULLED" = "0" ]; then
  echo "[pull] no artifacts pulled; cleaning up empty $AUDIT_DIR"
  rmdir "$AUDIT_DIR" 2>/dev/null || true
  exit 1
fi
```

### Preflight checks

`spark_setup.sh` (and ship-parallel.sh in the dgx repo) verify:
- `uv` installed + version
- `nvidia-smi` works + reports GPU
- `tmux` available (for long runs)
- Disk free at `$HOME`
- Required dirs exist (mkdir -p)

Add specific checks for keys/tokens when needed (anthropic, HF, etc.).

### Monitoring hints printed at end

Every "launch" script prints attach/tail/abort recipes at the end:

```bash
echo "monitor:"
echo "  ssh $SPARK 'tmux ls'"
echo "  ssh $SPARK 'tail -f $REMOTE_DIR/audit-runs/train-$TS.log'"
echo "abort:"
echo "  ssh $SPARK 'tmux kill-session -t <name>'"
```

So the operator never has to remember the magic incantations.

### tmux for long-running

Anything > 10 minutes of training should run inside tmux on DGX so it
survives ssh disconnect:

```bash
ssh "$SPARK" "tmux new -d -s '<name>' '<cmd> 2>&1 | tee <log>'"
```

For our autoresearch 5-min training, tmux is optional (`--tmux` flag on
`run.sh`); for the dgx repo's hours-long workloads, tmux is mandatory
(see `ship-parallel.sh`).

## Cross-repo file-equivalence map

| Concern | dgx repo | dgx-autoresearch |
|---|---|---|
| Mac → Spark code push | `scripts/sync-to-spark.sh` | `sync/push.sh` |
| Spark → Mac audit pull | `scripts/sync-audit-back.sh` | `sync/pull.sh` (default mode) |
| Spark → Mac inner-loop pull | n/a (different workflow) | `sync/pull.sh latest` |
| Spark → Mac corpus pull | `scripts/sync-corpus-back.sh` | n/a (autoresearch doesn't have corpus) |
| Inner-loop wrapper | n/a (Mac doesn't run their tight loop) | `sync/run.sh` |
| First-time setup | (manual, in journal) | `sync/spark_setup.sh` |
| Long parallel orchestration | `scripts/ship-parallel.sh` | n/a yet (overnight is single-train) |

If autoresearch ever needs a `ship-*.sh`-shaped multi-session orchestrator
(e.g., "run 4 parallel autoresearch loops on different cohort splits"), we
adopt the dgx repo's pattern verbatim.

## When to update

When **anything** in this convention changes (new exclude, new pattern,
new safety check), update:

1. The 4 scripts in this dir
2. This README's "Convention v1" section (bump to v2 + add migration note)
3. The dgx repo's parallel scripts at the same time, OR file an issue
   noting the divergence so the parallel agent picks it up next iteration

That's the manual-sync discipline. There's no automation; it relies on
explicit attention.
