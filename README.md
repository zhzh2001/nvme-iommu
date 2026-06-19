# NVMe IOMMU Benchmark Testsuite

This directory contains the testsuite designed to measure and analyze Linux IOMMU overhead on high-performance NVMe storage.

## 1. Testsuite Structure

* **[run_nvme_bench.sh](file:///home/paleshell/src/iomte/nvme_testsuite/run_nvme_bench.sh)**: Automates FIO benchmarks for 5 configurations (defaults to 1 run of 30 seconds per workload).
* **[trace_nvme_dma.sh](file:///home/paleshell/src/iomte/nvme_testsuite/trace_nvme_dma.sh)**: Profiles the DMA and IOMMU event counts/bytes for each of the 5 workloads (10s runs each) using `bpftrace`.
* **[parse_results.py](file:///home/paleshell/src/iomte/nvme_testsuite/parse_results.py)**: Processes FIO logs.
  * If multiple runs exist, it computes the **run-to-run standard deviation** across trials.
  * If only a single run exists, it automatically extracts the **internal temporal/per-operation standard deviation** from the FIO logs (e.g. `bw_dev` for bandwidth and `stddev` for latency).
* **[plot_nvme_overhead.py](file:///home/paleshell/src/iomte/nvme_testsuite/plot_nvme_overhead.py)**: Plots the latest runs for each tested mode side-by-side with error bars.
* **`results/`**: Directory where FIO logs and summaries are saved.

---

## 2. Performance Comparison (Single-Run with Internal StdDev)

* **Kernel**: `7.0.11-1-cachyos` (unmodified kernel)
* **Device**: `nvme0n1`
* **No IOMMU**: `intel_iommu=off` or `iommu=off`
* **Passthrough Mode**: `intel_iommu=on iommu=pt` or `iommu=pt`
* **Strict Mode**: `intel_iommu=on iommu.strict=1`
* **Deferred Mode**: `intel_iommu=on iommu.strict=0`

### Table 1: IOPS & Bandwidth (Single Run ± Internal StdDev)

| Job Name | Operations | No IOMMU (Baseline) | Deferred Mode | Strict Mode |
| :--- | :---: | :---: | :---: | :---: |
| **randread_4k** | Read IOPS | 195,307.14 ± 926.17 | 203,953.94 ± 764.48 | 227,000.10 ± 819.47 |
| | Read Bandwidth | 762.92 ± 3.62 MB/s | 796.70 ± 2.99 MB/s | 886.72 ± 3.20 MB/s |
| **randwrite_4k** | Write IOPS | 34,493.59 ± 3,581.13 | 33,985.74 ± 3,316.61 | 36,910.64 ± 2,666.01 |
| | Write Bandwidth | 134.74 ± 13.99 MB/s | 132.76 ± 12.96 MB/s | 144.18 ± 10.41 MB/s |
| **randrw_70_30** | Read IOPS | 60,176.55 ± 4,933.29 | 56,297.22 ± 5,466.70 | 56,832.12 ± 4,825.42 |
| | Write IOPS | 25,869.64 ± 2,116.56 | 24,204.55 ± 2,342.43 | 24,432.72 ± 2,072.18 |
| **seqread_128k** | Read IOPS | 9,191.81 ± 395.05 | 9,730.83 ± 40.54 | 9,337.69 ± 390.45 |
| | Read Bandwidth | 1,148.98 ± 49.38 MB/s | 1,216.35 ± 5.07 MB/s | 1,167.21 ± 48.80 MB/s |
| **seqwrite_128k** | Write IOPS | 3,497.64 ± 741.99 | 4,484.31 ± 500.85 | 4,385.26 ± 463.97 |
| | Write Bandwidth | 437.20 ± 92.75 MB/s | 560.54 ± 62.61 MB/s | 548.16 ± 58.00 MB/s |

### Table 2: Latency (Single Run ± Internal StdDev)

| Job Name | Metric | No IOMMU Latency (us) | Deferred Mode Latency (us) | Strict Mode Latency (us) |
| :--- | :---: | :---: | :---: | :---: |
| **randread_4k** | Read Latency | 2,620.63 ± 1,761.19 | 2,509.51 ± 1,335.40 | 2,254.72 ± 1,489.08 |
| **randwrite_4k** | Write Latency | 14,841.57 ± 46,073.89 | 15,063.43 ± 34,693.58 | 13,869.75 ± 24,077.65 |
| **randrw_70_30** | Read Latency | 7,079.96 ± 15,914.28 | 7,404.14 ± 14,261.14 | 7,814.35 ± 14,461.12 |
| | Write Latency | 3,318.39 ± 12,421.19 | 3,923.03 ± 13,645.15 | 2,773.70 ± 10,620.07 |
| **seqread_128k** | Read Latency | 13,921.92 ± 6,676.03 | 13,150.86 ± 1,192.87 | 13,704.79 ± 5,905.25 |
| **seqwrite_128k** | Write Latency | 36,586.02 ± 67,821.19 | 28,537.89 ± 35,827.72 | 29,179.08 ± 38,566.34 |

---

## 3. Why is "No IOMMU" Performance Worse?

In several benchmarks (notably `randread_4k` and `seqwrite_128k`), disabling the IOMMU entirely resulted in **worse** performance and higher latency. This is a known architectural phenomenon on modern x86 platforms:

1. **Interrupt Remapping Disabled**:
   Disabling the IOMMU (`intel_iommu=off` or `iommu=off`) automatically disables **Interrupt Remapping** (part of Intel VT-d). Interrupt remapping is required to balance Message Signaled Interrupts (MSI-X) across many CPU cores. Without it, the kernel falls back to legacy APIC routing, which forces all NVMe controller interrupts onto a single CPU core (usually CPU 0). This single core gets saturated with interrupt processing, bottlenecking the entire I/O queue.
   
2. **SWIOTLB Bounce Buffer Overhead**:
   Even with the IOMMU disabled, the kernel still allocates SWIOTLB memory. Depending on motherboard alignment constraints and PCIe bridges, certain transfers may fall back to SWIOTLB bounce buffers, introducing extra memory-copy overhead.

3. **Multi-Queue Affinity Breakage**:
   Modern NVMe drivers map hardware queues directly to specific CPU cores. Disabling IOMMU hardware translation disrupts this CPU affinity, causing inter-processor interrupts (IPIs) and cache-line bouncing.

### The Solution: Use Passthrough Mode (`iommu=pt`)
To measure the true "zero-translation" baseline, you should use **Passthrough Mode** (`iommu=pt` or `intel_iommu=on iommu=pt`) instead of `iommu=off`. 
* Passthrough mode bypasses DMA address translation (1-to-1 direct mapping), giving zero translation overhead.
* Crucially, because the IOMMU hardware remains active, **Interrupt Remapping and MSI-X core balancing remain fully enabled**. This isolates the translation cost without degrading the system's interrupt subsystem.
