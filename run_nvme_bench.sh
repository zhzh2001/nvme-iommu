#!/bin/bash
# run_nvme_bench.sh — Automate NVMe benchmarks under various IOMMU settings
set -euo pipefail

# Ensure we are in the script's directory
cd "$(dirname "$0")"

MODE=${1:-}
RUNS=${2:-10}  # Number of FIO runs per workload, defaults to 10
RUNTIME=${3:-30} # Runtime per FIO run in seconds, defaults to 30

if [ -z "$MODE" ]; then
    # Try to auto-detect mode from /sys/class/iommu and /proc/cmdline
    if [ ! -d /sys/class/iommu ] || [ -z "$(ls -A /sys/class/iommu 2>/dev/null)" ]; then
        MODE="no_iommu"
    else
        CMDLINE=$(cat /proc/cmdline)
        if [[ "$CMDLINE" =~ "iommu=pt" || "$CMDLINE" =~ "iommu.passthrough=1" ]]; then
            MODE="passthrough"
        elif [[ "$CMDLINE" =~ "iommu.strict=1" ]]; then
            MODE="strict"
        else
            MODE="deferred"
        fi
    fi
fi

# Map any alternative user inputs to standard mode names
if [ "$MODE" = "no-iommu" ] || [ "$MODE" = "no iommu" ]; then
    MODE="no_iommu"
fi
if [ "$MODE" = "pt" ] || [ "$MODE" = "pass" ]; then
    MODE="passthrough"
fi

RESULTS_DIR="results/${MODE}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

echo "================================================="
echo "Kernel: $(uname -r)"
echo "Command Line: $(cat /proc/cmdline)"
echo "Selected Mode: $MODE"
echo "Number of Runs: $RUNS"
echo "Runtime per Run: $RUNTIME seconds"
echo "Results will be saved to: $RESULTS_DIR"
echo "================================================="

# Create a test directory for FIO files on the NVMe drive
TEST_DIR="fio_test_dir"
mkdir -p "$TEST_DIR"
TEST_FILE="$TEST_DIR/fio_bench.img"

run_fio_job() {
    local job_name=$1
    local rw=$2
    local bs=$3
    local iodepth=$4
    local numjobs=$5
    local extra_args=${6:-""}
    
    echo ""
    echo "[*] Running FIO job: $job_name ($rw, bs=$bs, iodepth=$iodepth, jobs=$numjobs) — $RUNS runs..."
    
    for run in $(seq 1 "$RUNS"); do
        echo "    Run $run/$RUNS..."
        # Run FIO with json+text combined output
        fio --name="${job_name}_run${run}" \
            --ioengine=io_uring \
            --rw="$rw" \
            --bs="$bs" \
            --direct=1 \
            --iodepth="$iodepth" \
            --numjobs="$numjobs" \
            --size=1G \
            --runtime="$RUNTIME" \
            --time_based \
            --group_reporting \
            --filename="$TEST_FILE" \
            $extra_args \
            --output-format=normal,json \
            --output="$RESULTS_DIR/${job_name}_run${run}.log"
            
        # Cooldown sleep to let NVMe cache clear
        if [ "$run" -lt "$RUNS" ]; then
            sleep 15
        fi
    done
}

# 1. Random Read 4KB (Metadata/IOMMU Mapping Max Stress)
run_fio_job "randread_4k" "randread" "4k" 128 4

# 2. Random Write 4KB (Write Path Mapping Stress)
run_fio_job "randwrite_4k" "randwrite" "4k" 128 4

# 3. Mixed Random Read/Write 70/30
run_fio_job "randrw_70_30" "randrw" "4k" 128 4 "--rwmixread=70"

# 4. Sequential Read 128KB (High Bandwidth / Lower Mapping Rate per MB)
run_fio_job "seqread_128k" "read" "128k" 32 4

# 5. Sequential Write 128KB
run_fio_job "seqwrite_128k" "write" "128k" 32 4

# Cleanup test file to reclaim space
rm -f "$TEST_FILE"

echo ""
echo "================================================="
echo "   NVMe Benchmarks Completed Successfully!"
echo "   Processing results..."
echo "================================================="

# Call the standalone python script to parse results
if [ -f "./parse_results.py" ]; then
    python3 ./parse_results.py "$RESULTS_DIR"
else
    echo "[!] parse_results.py not found in current directory."
fi
