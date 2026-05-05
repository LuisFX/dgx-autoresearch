#!/usr/bin/env python3
"""
Backfill missing experiment data from log files and TSV data.

Task 1: Create JSON journal files for experiments with logs but no journal
Task 2: Merge root results.tsv with results/results.tsv into unified output
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import argparse

BASE_DIR = Path(__file__).parent.parent
LOGS_DIR = BASE_DIR / "results" / "logs"
JOURNAL_DIR = BASE_DIR / "results" / "journal"
ROOT_TSV = BASE_DIR / "results.tsv"
RESULTS_TSV = BASE_DIR / "results" / "results.tsv"
OUTPUT_TSV = BASE_DIR / "results" / "unified_results.tsv"


def get_file_timestamp(filepath: Path) -> str:
    """Get modification time of file in ISO 8601 format."""
    mtime = os.path.getmtime(filepath)
    dt = datetime.fromtimestamp(mtime)
    return dt.isoformat(timespec='seconds') + "+00:00"


def parse_log_file(log_path: Path) -> Dict[str, Any]:
    """Extract structured data from a log file."""
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    results = {}

    # Extract model config
    config_match = re.search(r"Model config: ({.*?})", content)
    if config_match:
        config_str = config_match.group(1)
        try:
            results['model_config'] = json.loads(config_str)
        except json.JSONDecodeError:
            pass

    # Extract parameter counts section
    param_section = {}
    # Look for parameter count lines like "  wte                     : 4,194,304"
    for line in content.split('\n'):
        if ':' in line and any(param in line for param in ['wte', 'value_embeds', 'lm_head', 'transformer_matrices', 'scalars']):
            parts = line.split(':')
            if len(parts) == 2:
                param_name = parts[0].strip()
                param_value_str = parts[1].strip().replace(',', '')
                try:
                    param_value = int(param_value_str)
                    param_section[param_name] = param_value
                except ValueError:
                    pass
    if param_section:
        results['params'] = param_section

    # Extract final metrics section (after "---")
    if '---' in content:
        final_section = content.split('---')[-1]
        metrics_map = {
            'val_bpb': 'val_bpb',
            'training_seconds': 'training_seconds',
            'total_seconds': 'total_seconds',
            'peak_vram_mb': 'peak_vram_mb',
            'mfu_percent': 'mfu_percent',
            'total_tokens_M': 'total_tokens_M',
            'num_steps': 'num_steps',
            'num_params_M': 'num_params_M',
            'depth': 'depth',
        }

        for key, metric in metrics_map.items():
            pattern = rf"{metric}:\s+([\d.]+)"
            match = re.search(pattern, final_section)
            if match:
                value_str = match.group(1)
                try:
                    # Try to parse as float, then int if no decimal
                    if '.' in value_str:
                        results[metric] = float(value_str)
                    else:
                        results[metric] = int(value_str)
                except ValueError:
                    pass

    # Extract last training step for reference
    step_pattern = r"step (\d+) \([\d.]+%\) \| loss: ([\d.]+)"
    matches = re.findall(step_pattern, content)
    if matches:
        last_step, last_loss = matches[-1]
        results['last_step'] = int(last_step)
        results['final_loss'] = float(last_loss)

    return results


def extract_memory_from_log(log_path: Path) -> Optional[float]:
    """Extract memory_gb from peak_vram_mb in log file."""
    data = parse_log_file(log_path)
    if 'peak_vram_mb' in data:
        return round(data['peak_vram_mb'] / 1024, 1)
    return None


def read_root_tsv() -> Dict[int, Dict[str, Any]]:
    """Read root results.tsv and return mapping of exp_id -> row data."""
    data = {}
    with open(ROOT_TSV, 'r') as f:
        lines = f.readlines()

    # Skip header (line 0)
    for idx, line in enumerate(lines[1:], start=0):
        parts = line.strip().split('\t')
        if len(parts) >= 5:
            commit, val_bpb, memory_gb, status, description = parts[0:5]
            try:
                data[idx] = {
                    'commit': commit,
                    'val_bpb': float(val_bpb),
                    'memory_gb': float(memory_gb),
                    'status': status,
                    'description': description,
                }
            except (ValueError, IndexError):
                pass

    return data


def read_results_tsv() -> Dict[int, Dict[str, Any]]:
    """Read results/results.tsv and return mapping of exp_id -> row data."""
    data = {}
    with open(RESULTS_TSV, 'r') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) >= 8:
                try:
                    exp_id = int(parts[0].replace('exp_', ''))
                    description = parts[1]
                    val_bpb = float(parts[2])
                    peak_mem_mb = float(parts[3])
                    memory_gb = float(parts[4])
                    steps = int(parts[5])
                    params_M = float(parts[6])
                    mfu = float(parts[7])

                    data[exp_id] = {
                        'description': description,
                        'val_bpb': val_bpb,
                        'peak_mem_mb': peak_mem_mb,
                        'memory_gb': memory_gb,
                        'steps': steps,
                        'params_M': params_M,
                        'mfu': mfu,
                    }
                except (ValueError, IndexError):
                    pass

    return data


def create_journal_entry(
    exp_id: int,
    log_path: Path,
    root_tsv_data: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    """Create a journal JSON entry from log file and TSV data."""

    log_data = parse_log_file(log_path)
    tsv_entry = root_tsv_data.get(exp_id, {})

    # Extract key metrics
    val_bpb = log_data.get('val_bpb') or tsv_entry.get('val_bpb')
    memory_gb = log_data.get('peak_vram_mb', 0)
    if memory_gb > 0:
        memory_gb = round(memory_gb / 1024, 1)
    else:
        memory_gb = tsv_entry.get('memory_gb')

    mfu_percent = log_data.get('mfu_percent')
    num_steps = log_data.get('num_steps')
    num_params_M = log_data.get('num_params_M')
    depth = log_data.get('depth')

    # Determine if crashed
    error = None
    if val_bpb == 0.0 or val_bpb is None:
        error = "crash"
        # For crash entries, nullify numeric results
        val_bpb = None
        mfu_percent = None
        num_steps = None

    # Build results dict
    results = {
        'val_bpb': val_bpb,
        'memory_gb': memory_gb,
    }
    if mfu_percent is not None:
        results['mfu_percent'] = mfu_percent
    if num_steps is not None:
        results['num_steps'] = num_steps
    if num_params_M is not None:
        results['num_params_M'] = num_params_M

    entry = {
        'id': exp_id,
        'description': tsv_entry.get('description', log_path.stem),
        'timestamp': get_file_timestamp(log_path),
        'hypothesis': None,
        'config_changes': [],
        'commit': tsv_entry.get('commit'),
        'results': results,
        'decision': tsv_entry.get('status', 'unknown'),
        'decision_reasoning': 'from results.tsv',
        'agent_notes': [],
        'error': error,
    }

    return entry


def backfill_journal_entries():
    """Backfill missing journal entries for exp 1-18 and 67-71."""

    # Mapping of log files to exp IDs
    exp_mappings = {
        'exp1_half_batch.log': 1,
        'exp2_quarter_batch.log': 2,
        'exp3_32batch.log': 3,
        'exp4_16batch.log': 4,
        'exp5_depth12.log': 5,
        'exp6_dim640.log': 6,
        'exp7_depth12_sysptxas.log': 7,
        'exp8_depth10.log': 8,
        'exp9_warmdown25.log': 9,
        'exp10_higher_matrixlr.log': 10,
        'exp11_warmdown70.log': 11,
        'exp12_warmdown90.log': 12,
        'exp13_muon_momentum_150.log': 13,
        'exp14_embed_lr_1.0.log': 14,
        'exp15_ssll.log': 15,
        'exp16_slll.log': 16,
        'exp17_llll.log': 17,
        'exp18_unembed_lr.log': 18,
        'exp67_scalar_lr0.25.log': 67,
        'exp68_embed_lr1.7.log': 68,
        'exp69_tied_ve_wte.log': 69,
        'exp70_rope_base1000.log': 70,
        'exp71_ve_gate64.log': 71,
    }

    # Create journal directory if needed
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)

    # Read root TSV
    root_tsv_data = read_root_tsv()

    backfilled_count = 0
    skipped_count = 0

    for log_filename, exp_id in exp_mappings.items():
        log_path = LOGS_DIR / log_filename
        journal_path = JOURNAL_DIR / f"exp_{exp_id:03d}.json"

        # Skip if already exists
        if journal_path.exists():
            print(f"  exp_{exp_id:03d}: journal already exists, skipping")
            skipped_count += 1
            continue

        # Check if log exists
        if not log_path.exists():
            print(f"  exp_{exp_id:03d}: log file not found ({log_filename})")
            continue

        # Create entry
        try:
            entry = create_journal_entry(exp_id, log_path, root_tsv_data)

            # Write JSON
            with open(journal_path, 'w') as f:
                json.dump(entry, f, indent=2)

            print(f"  exp_{exp_id:03d}: backfilled from {log_filename}")
            backfilled_count += 1
        except Exception as e:
            print(f"  exp_{exp_id:03d}: ERROR - {e}")

    print(f"\nBackfill complete: {backfilled_count} created, {skipped_count} already exist")


def merge_tsv_data():
    """Merge root TSV and results TSV into unified output."""

    # Read both sources
    root_data = read_root_tsv()
    results_data = read_results_tsv()

    # Merge: results_data overrides root_data for overlapping exp IDs
    all_exps = {}
    all_exps.update(root_data)
    all_exps.update(results_data)

    # Try to load git commits for exp 109+
    git_commits = {}
    try:
        # Load from journal JSON files if available
        for exp_id in sorted(all_exps.keys()):
            if exp_id >= 109:
                journal_path = JOURNAL_DIR / f"exp_{exp_id:03d}.json"
                if journal_path.exists():
                    try:
                        with open(journal_path, 'r') as f:
                            journal_data = json.load(f)
                            if journal_data.get('commit'):
                                git_commits[exp_id] = journal_data['commit']
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"Note: Could not load git commits: {e}")

    # Build unified output
    output_lines = [
        "exp_id\tcommit\tval_bpb\tmemory_gb\tsteps\tparams_M\tmfu\tstatus\tdescription"
    ]

    for exp_id in sorted(all_exps.keys()):
        exp_data = all_exps[exp_id]

        commit = exp_data.get('commit', '')
        if not commit and exp_id in git_commits:
            commit = git_commits[exp_id]

        val_bpb = exp_data.get('val_bpb', '')
        memory_gb = exp_data.get('memory_gb', '')
        steps = exp_data.get('steps', '')
        params_M = exp_data.get('params_M', '')
        mfu = exp_data.get('mfu', '')
        status = exp_data.get('status', '')
        description = exp_data.get('description', '')

        # Format values
        val_bpb_str = f"{val_bpb:.6f}" if isinstance(val_bpb, float) else str(val_bpb)
        memory_gb_str = f"{memory_gb:.1f}" if isinstance(memory_gb, float) else str(memory_gb)
        steps_str = str(steps) if steps else ''
        params_M_str = f"{params_M:.1f}" if isinstance(params_M, float) else str(params_M)
        mfu_str = f"{mfu:.2f}" if isinstance(mfu, float) else str(mfu)

        line = f"{exp_id}\t{commit}\t{val_bpb_str}\t{memory_gb_str}\t{steps_str}\t{params_M_str}\t{mfu_str}\t{status}\t{description}"
        output_lines.append(line)

    # Write output
    with open(OUTPUT_TSV, 'w') as f:
        f.write('\n'.join(output_lines))

    print(f"Merged TSV written to {OUTPUT_TSV}")
    print(f"  Total experiments: {len(all_exps)}")
    print(f"  Range: exp_0 to exp_{max(all_exps.keys())}")


def main():
    parser = argparse.ArgumentParser(
        description='Backfill missing experiment data from logs and TSV files'
    )
    parser.add_argument(
        '--backfill-journal',
        action='store_true',
        help='Backfill missing journal JSON entries from log files'
    )
    parser.add_argument(
        '--merge-tsv',
        action='store_true',
        help='Merge root TSV and results TSV into unified output'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run both backfill and merge tasks'
    )

    args = parser.parse_args()

    # Default to --all if no flags specified
    if not (args.backfill_journal or args.merge_tsv or args.all):
        args.all = True

    print("=" * 70)
    print("Backfill Data Script")
    print("=" * 70)

    if args.backfill_journal or args.all:
        print("\nTask 1: Backfilling journal entries...")
        backfill_journal_entries()

    if args.merge_tsv or args.all:
        print("\nTask 2: Merging TSV data...")
        merge_tsv_data()

    print("\n" + "=" * 70)
    print("Done!")


if __name__ == '__main__':
    main()
