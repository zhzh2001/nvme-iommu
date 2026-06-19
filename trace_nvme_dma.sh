#!/bin/bash
# trace_nvme_dma.sh — Trace DMA/IOMMU counts for each NVMe workload
set -euo pipefail

# Ensure we are in the script's directory
cd "$(dirname "$0")"

MODE=${1:-"strict"}
RESULTS_DIR="results/${MODE}_dma_trace"
mkdir -p "$RESULTS_DIR"

echo "================================================="
echo "   Starting NVMe DMA/IOMMU Tracing"
echo "   Mode: $MODE"
echo "   Results: $RESULTS_DIR"
echo "================================================="

# Create test directory and file
TEST_DIR="fio_test_dir"
mkdir -p "$TEST_DIR"
TEST_FILE="$TEST_DIR/fio_trace.img"

# Write bpftrace script to a temp file
BPF_FILE=$(mktemp /tmp/nvme_trace.XXXXXX.bt)
cat << 'EOF' > "$BPF_FILE"
tracepoint:iommu:map {
    @iommu_map_count = count();
    @iommu_map_bytes = sum(args.size);
}
tracepoint:iommu:unmap {
    @iommu_unmap_count = count();
    @iommu_unmap_bytes = sum(args.size);
}
tracepoint:dma:dma_map_sg {
    @dma_map_sg_count = count();
}
tracepoint:dma:dma_unmap_sg {
    @dma_unmap_sg_count = count();
}
kprobe:dma_map_page_attrs {
    @dma_map_page_count = count();
}
kprobe:dma_unmap_page_attrs {
    @dma_unmap_page_count = count();
}
EOF

run_traced_fio() {
    local job_name=$1
    local rw=$2
    local bs=$3
    local iodepth=$4
    local numjobs=$5
    local extra_args=${6:-""}
    
    echo ""
    echo "[*] Tracing FIO: $job_name..."
    
    # Start bpftrace
    sudo bpftrace "$BPF_FILE" > "$RESULTS_DIR/${job_name}_bpftrace.log" 2>&1 &
    BPF_PID=$!
    
    # Wait for bpftrace to attach
    sleep 4
    
    # Run FIO for 10 seconds
    fio --name="$job_name" \
        --ioengine=io_uring \
        --rw="$rw" \
        --bs="$bs" \
        --direct=1 \
        --iodepth="$iodepth" \
        --numjobs="$numjobs" \
        --size=1G \
        --runtime=10 \
        --time_based \
        --group_reporting \
        --filename="$TEST_FILE" \
        $extra_args > /dev/null 2>&1
        
    # Stop bpftrace
    sudo kill -SIGINT "$BPF_PID"
    wait "$BPF_PID" 2>/dev/null || true
    
    # Print brief summary of counts
    echo "    Completed. Trace Summary:"
    python3 -c "
import re
with open('$RESULTS_DIR/${job_name}_bpftrace.log') as f:
    content = f.read()
    
    def get_val(name):
        m = re.search(rf'{name}:\s*([0-9\-]+)', content)
        return int(m.group(1)) if m else 0
        
    imap = get_val('@iommu_map_count')
    ibytes = get_val('@iommu_map_bytes') / (1024 * 1024)
    iunmap = get_val('@iommu_unmap_count')
    dsg = get_val('@dma_map_sg_count')
    dpage = get_val('@dma_map_page_count')
    
    print(f'      DMA SG Maps: {dsg} | DMA Page Maps: {dpage}')
    print(f'      IOMMU Maps : {imap} ({ibytes:.1f} MB) | IOMMU Unmaps: {iunmap}')
"
}

# Run the 5 tracing configurations
run_traced_fio "randread_4k" "randread" "4k" 128 4
run_traced_fio "randwrite_4k" "randwrite" "4k" 128 4
run_traced_fio "randrw_70_30" "randrw" "4k" 128 4 "--rwmixread=70"
run_traced_fio "seqread_128k" "read" "128k" 32 4
run_traced_fio "seqwrite_128k" "write" "128k" 32 4

# Cleanup test file and bpftrace temp file
rm -f "$TEST_FILE"
rm -f "$BPF_FILE"

echo ""
echo "================================================="
echo "   NVMe Tracing Completed Successfully!"
echo "   Trace results saved in $RESULTS_DIR"
echo "================================================="
