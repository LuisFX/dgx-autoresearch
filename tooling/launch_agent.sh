#!/usr/bin/env bash
# Launch a fresh Claude Code session for the autoresearch experiment loop on GB10.
# Adapted from shared/run_claude_agent.sh for local DGX Spark execution.
#
# Usage:
#   ./launch_agent.sh                    # Default: 2 hour timeout
#   ./launch_agent.sh --timeout 36000    # 10 hour overnight run
#   ./launch_agent.sh --timeout 7200     # 2 hour run
#
# Outputs:
#   results/agent/agent_output.json  - Full Claude JSON output (token usage, cost)
#   results/agent/agent.log          - Extracted text result
#   results/agent/agent.err          - Stderr
#   results/agent/agent_stats.json   - Usage/cost summary
#   results/metrics/agent_session.jsonl - System metrics during run
#   results/logs/                     - Training logs (created by agent)
#   results/journal/                  - Experiment journal (created by agent)
#   results.tsv                       - Results tracker (created by agent)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ANGLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$ANGLE_DIR/../repo" && pwd)"
RESULTS_DIR="$ANGLE_DIR/results"
AGENT_DIR="$RESULTS_DIR/agent"
METRICS_DIR="$RESULTS_DIR/metrics"
LOGS_DIR="$RESULTS_DIR/logs"

# Parse args
TIMEOUT_SECONDS=7200  # 2 hours default
while [[ $# -gt 0 ]]; do
    case $1 in
        --timeout) TIMEOUT_SECONDS="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# Setup directories
mkdir -p "$AGENT_DIR" "$METRICS_DIR" "$LOGS_DIR" "$RESULTS_DIR/journal" "$RESULTS_DIR/charts"

# Timestamp for this session
SESSION_TS=$(date +%Y%m%d_%H%M%S)

echo "============================================================"
echo "  Autoresearch GB10 Agent Launcher"
echo "============================================================"
echo "  Repo:     $REPO_DIR"
echo "  Results:  $RESULTS_DIR"
echo "  Timeout:  ${TIMEOUT_SECONDS}s ($(( TIMEOUT_SECONDS / 3600 ))h $(( (TIMEOUT_SECONDS % 3600) / 60 ))m)"
echo "  Session:  $SESSION_TS"
echo "  Claude:   $(claude --version 2>/dev/null | head -1)"
echo ""

# Verify GPU is ready
echo "GPU Status:"
nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,power.draw \
    --format=csv,noheader 2>/dev/null || echo "  nvidia-smi unavailable"
echo ""

# Verify data exists
if [[ ! -d "$HOME/.cache/autoresearch/data" ]]; then
    echo "ERROR: Data not found. Run: cd $REPO_DIR && uv run prepare.py"
    exit 1
fi

# Start system monitor in background
cd "$SCRIPT_DIR"
python3 monitor.py start --output "$METRICS_DIR/agent_session_${SESSION_TS}.jsonl"
echo ""

# Build the prompt
# The agent reads program.md for the experiment loop logic, but we override
# all output paths to point at our results directory structure.
RESULTS_TSV="$ANGLE_DIR/results.tsv"
JOURNAL_DIR="$RESULTS_DIR/journal"

CLAUDE_PROMPT="Read program.md for the experiment loop logic. The setup is already done:
- Branch: autoresearch/blackwell-mar11 (you're on it)
- Data: prepared in ~/.cache/autoresearch/
- Previous experiments: already recorded in $RESULTS_TSV (read it to see what's been tried)
- NOTE: HEAD may be a crashed/discarded experiment. Check git log and results.tsv. If the last entry is a crash or discard, git reset --hard to the last 'keep' commit before starting new experiments.

Then run the experiment loop.

## GB10 Blackwell Context
- NVIDIA DGX Spark with GB10 GPU (sm_121, 128GB VRAM)
- FA3 replaced with PyTorch SDPA (already done in train.py)
- FLOPS constant: 213 TFLOPS (GB10 measured, not H100)
- GB10 is ~10x slower than H100: baseline gets ~93 steps in 5min
- Key insight: we are STEP-LIMITED, not VRAM-limited (44GB of 128GB used)
- Explore: batch sizes, learning rate schedules, architecture changes, larger models

## CRITICAL: Output Paths (OVERRIDE program.md defaults)

All output MUST go to the results directory, NOT the repo directory.

### Training logs
Redirect every training run to the logs directory:
  uv run train.py > $LOGS_DIR/<experiment_name>.log 2>&1
  grep '^val_bpb:\|^peak_vram_mb:' $LOGS_DIR/<experiment_name>.log

Use descriptive names like: exp01_halve_batch.log, exp02_quarter_batch.log, etc.

### results.tsv
Write ALL experiment results (keep, discard, AND crash) to:
  $RESULTS_TSV

This file already has a header and baseline. Append one line per experiment.
Format: commit<TAB>val_bpb<TAB>memory_gb<TAB>status<TAB>description
Use 7-char commit hash for keeps, '-------' for discards/crashes.

### Experiment journal
After EACH experiment, write a JSON file to:
  $JOURNAL_DIR/exp_NNN.json

where NNN is the experiment number (001, 002, etc). exp_000.json (baseline) already exists.

JSON format:
{
  \"id\": 1,
  \"description\": \"short description of what was tried\",
  \"timestamp\": \"YYYY-MM-DDTHH:MM:SS+00:00\",
  \"hypothesis\": \"why you think this will improve val_bpb\",
  \"config_changes\": [{\"param\": \"TOTAL_BATCH_SIZE\", \"old\": \"2**19\", \"new\": \"2**18\"}],
  \"commit\": \"abc1234 or null if discarded\",
  \"results\": {\"val_bpb\": 1.234, \"memory_gb\": 44.0, \"mfu_percent\": 16.0, \"num_steps\": 93, \"num_params_M\": 50.3},
  \"decision\": \"keep|discard|crash\",
  \"decision_reasoning\": \"why you kept or discarded this experiment\",
  \"agent_notes\": [\"any observations worth recording\"],
  \"error\": null
}

You can write these with a simple python one-liner or bash heredoc.

### System metrics
The system monitor is already running externally. You do NOT need to manage it.

## IMPORTANT REMINDERS
- NEVER STOP: Run experiments until interrupted. Do not ask to continue.
- Write results.tsv AND journal entries AFTER EVERY experiment, not just keeps.
- Use descriptive log filenames, not 'run.log'.

Start the loop now. Do not ask for confirmation."

# Record start
START_EPOCH=$(date +%s)

echo "Launching Claude Code agent..."
echo "  (Use Ctrl+C to stop)"
echo "============================================================"
echo ""

# Launch fresh Claude session (unset CLAUDECODE to allow nested launch)
cd "$REPO_DIR"
unset CLAUDECODE 2>/dev/null || true
timeout "$TIMEOUT_SECONDS" claude --dangerously-skip-permissions \
    -p "$CLAUDE_PROMPT" \
    --allowedTools "Bash,Read,Edit,Write,Glob,Grep" \
    --output-format json \
    --no-session-persistence \
    --model sonnet \
    > "$AGENT_DIR/agent_output_${SESSION_TS}.json" 2>"$AGENT_DIR/agent_${SESSION_TS}.err" || true

EXIT_CODE=$?
END_EPOCH=$(date +%s)
DURATION=$(( END_EPOCH - START_EPOCH ))

# Stop system monitor
cd "$SCRIPT_DIR"
python3 monitor.py stop 2>/dev/null || true

echo ""
echo "============================================================"
echo "  Agent Session Complete"
echo "============================================================"
echo "  Exit code: $EXIT_CODE"
echo "  Duration:  ${DURATION}s ($(( DURATION / 3600 ))h $(( (DURATION % 3600) / 60 ))m $(( DURATION % 60 ))s)"
echo "  Output:    $AGENT_DIR/agent_output_${SESSION_TS}.json"
echo "  Size:      $(du -sh "$AGENT_DIR/agent_output_${SESSION_TS}.json" 2>/dev/null | cut -f1) "
echo ""

# Extract cost/usage stats from JSON output
AGENT_OUTPUT="$AGENT_DIR/agent_output_${SESSION_TS}.json"
if [[ -s "$AGENT_OUTPUT" ]]; then
    python3 -c "
import json, sys

try:
    data = json.load(open('$AGENT_OUTPUT'))

    # Navigate the JSON structure to find usage
    usage = data.get('usage', data.get('result', {}).get('usage', {}))
    cost = data.get('cost_usd', data.get('result', {}).get('cost_usd', 'unknown'))
    input_tokens = usage.get('input_tokens', data.get('input_tokens', 'unknown'))
    output_tokens = usage.get('output_tokens', data.get('output_tokens', 'unknown'))
    cache_read = usage.get('cache_read_input_tokens', 0)
    cache_create = usage.get('cache_creation_input_tokens', 0)

    stats = {
        'session': '$SESSION_TS',
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'cache_read_tokens': cache_read,
        'cache_create_tokens': cache_create,
        'cost_usd': cost,
        'duration_seconds': $DURATION,
        'exit_code': $EXIT_CODE,
        'timeout_seconds': $TIMEOUT_SECONDS,
    }

    with open('$AGENT_DIR/agent_stats_${SESSION_TS}.json', 'w') as f:
        json.dump(stats, f, indent=2)

    print(f'  Input tokens:  {input_tokens:,}' if isinstance(input_tokens, int) else f'  Input tokens:  {input_tokens}')
    print(f'  Output tokens: {output_tokens:,}' if isinstance(output_tokens, int) else f'  Output tokens: {output_tokens}')
    print(f'  Cache read:    {cache_read:,}' if isinstance(cache_read, int) else f'  Cache read:    {cache_read}')
    print(f'  Cost (USD):    \${cost}' if isinstance(cost, (int, float)) else f'  Cost (USD):    {cost}')
except Exception as e:
    print(f'  Could not parse JSON output: {e}')
    with open('$AGENT_OUTPUT') as f:
        content = f.read()
    print(f'  Raw size: {len(content)} bytes')
    print(f'  First 300 chars: {content[:300]}')
" 2>&1 || true

    # Extract text result to a readable log
    python3 -c "
import json
try:
    data = json.load(open('$AGENT_OUTPUT'))
    result = data.get('result', data.get('text', data.get('content', '')))
    if isinstance(result, dict):
        result = result.get('text', str(result))
    if isinstance(result, list):
        result = '\n'.join(str(r) for r in result)
    with open('$AGENT_DIR/agent_${SESSION_TS}.log', 'w') as f:
        f.write(str(result))
    print(f'  Agent log: $AGENT_DIR/agent_${SESSION_TS}.log')
except Exception as e:
    print(f'  Could not extract text: {e}')
" 2>&1 || true
fi

# Show stderr if any
if [[ -s "$AGENT_DIR/agent_${SESSION_TS}.err" ]]; then
    echo ""
    echo "--- stderr (last 20 lines) ---"
    tail -20 "$AGENT_DIR/agent_${SESSION_TS}.err"
fi

# Show results
echo ""
echo "--- Results ---"
if [[ -f "$ANGLE_DIR/results.tsv" ]]; then
    echo "results.tsv:"
    cat "$ANGLE_DIR/results.tsv"
else
    echo "No results.tsv found (agent may not have created it)"
fi

echo ""
echo "--- Experiment Journal ---"
ls -lh "$RESULTS_DIR/journal"/ 2>/dev/null || echo "No journal entries"

echo ""
echo "--- Experiment Logs ---"
ls -lh "$LOGS_DIR"/ 2>/dev/null || echo "No logs created"

echo ""
echo "--- System Metrics ---"
ls -lh "$METRICS_DIR"/ 2>/dev/null || echo "No metrics"

echo ""
echo "To generate charts: cd $SCRIPT_DIR && python3 analyze.py"
echo "============================================================"
