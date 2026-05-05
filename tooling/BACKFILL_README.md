# Backfill Data Script

This script performs two tasks to consolidate experiment data:

## Task 1: Backfill Missing Journal Entries

Creates JSON journal files for experiments 1-18 and 67-71 that have log files but no corresponding journal JSON.

**Process:**
- Reads log files from `results/logs/`
- Extracts metrics: val_bpb, memory_gb, mfu_percent, num_steps, num_params_M, depth
- Merges with root `results.tsv` data for commit hashes, status, and descriptions
- Creates journal JSON entries matching the standard schema
- Uses file modification time for timestamps
- Marks crashed experiments (val_bpb = 0.0) with error: "crash"

**Output:** 23 new journal files in `results/journal/` (exp_001 through exp_018, exp_067 through exp_071)

## Task 2: Create Unified Results TSV

Merges data from multiple sources into a single consolidated results file.

**Input sources:**
1. Root `results.tsv` (experiments 0-108)
2. `results/results.tsv` (experiments 109-150)
3. Journal JSON files (for commit hashes)

**Output schema:**
```
exp_id	commit	val_bpb	memory_gb	steps	params_M	mfu	status	description
```

**Output:** `results/unified_results.tsv` with 130 experiments (0-129)

## Usage

```bash
# Run both tasks (default)
python3 backfill_data.py --all

# Run only backfill
python3 backfill_data.py --backfill-journal

# Run only merge
python3 backfill_data.py --merge-tsv
```

## Notes

- Journal backfill skips existing entries (safe to re-run)
- TSV merge is idempotent (overwrites output file)
- All timestamps are in ISO 8601 format with UTC timezone
- Crash experiments have `error: "crash"` and nullified numeric metrics
- Memory values are automatically converted from MB to GB where needed
