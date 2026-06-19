#!/usr/bin/env python3
import os
import glob
import json
import numpy as np
import matplotlib.pyplot as plt

def get_latest_dir(mode_name):
    dirs = glob.glob(f"results/{mode_name}_*")
    # Filter to actual directories
    dirs = [d for d in dirs if os.path.isdir(d)]
    if not dirs:
        return None
    # Sort by creation time
    return max(dirs, key=os.path.getctime)

def load_summary(results_dir):
    if not results_dir:
        return None
    json_path = os.path.join(results_dir, "summary.json")
    if not os.path.exists(json_path):
        return None
    with open(json_path, 'r') as f:
        return json.load(f)

def main():
    # Find latest results directories for the four modes
    modes = ['no_iommu', 'passthrough', 'deferred', 'strict']
    dirs = {m: get_latest_dir(m) for m in modes}
    summaries = {m: load_summary(dirs[m]) for m in modes}
    
    # Check if we have at least one summary to plot
    active_modes = [m for m in modes if summaries[m] is not None]
    if not active_modes:
        print("Error: No summary.json files found to plot.")
        print("Please run benchmarks first (e.g. ./run_nvme_bench.sh deferred)")
        return
        
    print("Plotting data from:")
    for m in active_modes:
        print(f"  {m:<10} -> {dirs[m]}")
        
    # Extract data for Random workloads (IOPS)
    random_labels = ['randread_4k', 'randwrite_4k', 'randrw_70_30']
    random_names = ['Random Read 4K', 'Random Write 4K', 'Mixed 70/30 (R+W)']
    
    # Extract data for Sequential workloads (MB/s)
    seq_labels = ['seqread_128k', 'seqwrite_128k']
    seq_names = ['Seq Read 128K', 'Seq Write 128K']
    
    # We want to retrieve mean and std for each mode and workload
    def get_val_std(summary, wl, metric):
        if not summary or wl not in summary or metric not in summary[wl]:
            return 0.0, 0.0
        return summary[wl][metric]

    # Data structures for plotting
    plot_data_rand = {m: [] for m in active_modes}
    plot_std_rand = {m: [] for m in active_modes}
    
    plot_data_seq = {m: [] for m in active_modes}
    plot_std_seq = {m: [] for m in active_modes}
    
    for m in active_modes:
        s = summaries[m]
        
        # Random Read 4K
        mean, std = get_val_std(s, 'randread_4k', 'Read IOPS')
        plot_data_rand[m].append(mean)
        plot_std_rand[m].append(std)
        
        # Random Write 4K
        mean, std = get_val_std(s, 'randwrite_4k', 'Write IOPS')
        plot_data_rand[m].append(mean)
        plot_std_rand[m].append(std)
        
        # Mixed Random 70/30 (sum of read and write IOPS)
        rmean, rstd = get_val_std(s, 'randrw_70_30', 'Read IOPS')
        wmean, wstd = get_val_std(s, 'randrw_70_30', 'Write IOPS')
        plot_data_rand[m].append(rmean + wmean)
        # Standard deviation of the sum: sqrt(std1^2 + std2^2) assuming independence
        plot_std_rand[m].append(np.sqrt(rstd**2 + wstd**2))
        
        # Sequential Read 128K
        mean, std = get_val_std(s, 'seqread_128k', 'Read Bandwidth (MB/s)')
        plot_data_seq[m].append(mean)
        plot_std_seq[m].append(std)
        
        # Sequential Write 128K
        mean, std = get_val_std(s, 'seqwrite_128k', 'Write Bandwidth (MB/s)')
        plot_data_seq[m].append(mean)
        plot_std_seq[m].append(std)

    # Set up matplotlib figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    x_rand = np.arange(len(random_names))
    x_seq = np.arange(len(seq_names))
    
    # Configure bar positions based on how many modes are active
    n_modes = len(active_modes)
    width = 0.8 / n_modes if n_modes > 1 else 0.4
    offsets = [(i - (n_modes - 1) / 2.0) * width for i in range(n_modes)]
        
    colors = {
        'no_iommu': '#2ca02c',  # Green
        'passthrough': '#9467bd', # Purple
        'deferred': '#1f77b4',  # Blue
        'strict': '#d62728'     # Red
    }
    labels = {
        'no_iommu': 'No IOMMU (Baseline)',
        'passthrough': 'Passthrough Mode',
        'deferred': 'Deferred Mode',
        'strict': 'Strict Mode'
    }

    # Plot Random workloads
    for idx, m in enumerate(active_modes):
        ax1.bar(x_rand + offsets[idx], plot_data_rand[m], width, 
                yerr=plot_std_rand[m], capsize=5, 
                label=labels[m], color=colors[m])
        
    ax1.set_ylabel('Throughput (IOPS) — Higher is Better', fontsize=12)
    ax1.set_title('Random 4KB Workloads Throughput', fontsize=14, fontweight='bold')
    ax1.set_xticks(x_rand)
    ax1.set_xticklabels(random_names, fontsize=11)
    ax1.grid(axis='y', linestyle='--', alpha=0.7)
    ax1.legend(fontsize=10)
    
    # Plot Sequential workloads
    for idx, m in enumerate(active_modes):
        ax2.bar(x_seq + offsets[idx], plot_data_seq[m], width, 
                yerr=plot_std_seq[m], capsize=5, 
                label=labels[m], color=colors[m])
        
    ax2.set_ylabel('Bandwidth (MB/s) — Higher is Better', fontsize=12)
    ax2.set_title('Sequential 128KB Workloads Throughput', fontsize=14, fontweight='bold')
    ax2.set_xticks(x_seq)
    ax2.set_xticklabels(seq_names, fontsize=11)
    ax2.grid(axis='y', linestyle='--', alpha=0.7)
    ax2.legend(fontsize=10)

    # Annotate overhead percentages if base mode (no_iommu, passthrough, or deferred) is available
    base_mode = None
    if 'no_iommu' in active_modes:
        base_mode = 'no_iommu'
    elif 'passthrough' in active_modes:
        base_mode = 'passthrough'
    elif 'deferred' in active_modes:
        base_mode = 'deferred'
        
    if base_mode:
        # Annotate Random panel
        for i in range(len(random_names)):
            base_val = plot_data_rand[base_mode][i]
            if base_val == 0: continue
            for idx, m in enumerate(active_modes):
                if m == base_mode: continue
                val = plot_data_rand[m][i]
                diff = ((val - base_val) / base_val) * 100
                y_pos = val + plot_std_rand[m][i]
                ax1.annotate(f"{diff:+.1f}%",
                             xy=(x_rand[i] + offsets[idx], y_pos),
                             xytext=(0, 3), textcoords="offset points",
                             ha='center', va='bottom', fontsize=9, fontweight='bold',
                             color='green' if diff >= 0 else 'red')
                             
        # Annotate Sequential panel
        for i in range(len(seq_names)):
            base_val = plot_data_seq[base_mode][i]
            if base_val == 0: continue
            for idx, m in enumerate(active_modes):
                if m == base_mode: continue
                val = plot_data_seq[m][i]
                diff = ((val - base_val) / base_val) * 100
                y_pos = val + plot_std_seq[m][i]
                ax2.annotate(f"{diff:+.1f}%",
                             xy=(x_seq[i] + offsets[idx], y_pos),
                             xytext=(0, 3), textcoords="offset points",
                             ha='center', va='bottom', fontsize=9, fontweight='bold',
                             color='green' if diff >= 0 else 'red')

    plt.tight_layout()
    output_path = "results/nvme_overhead_comparison.png"
    plt.savefig(output_path, dpi=300)
    print(f"Comparison plot saved to {output_path}")

if __name__ == "__main__":
    main()
