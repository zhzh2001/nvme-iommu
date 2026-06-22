#!/usr/bin/env python3
import sys
import os
import glob
import json
import statistics

def parse_fio_file(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
    json_start = content.find('{')
    if json_start == -1:
        raise ValueError(f"No JSON found in {file_path}")
    
    d, _ = json.JSONDecoder().raw_decode(content[json_start:])
    job = d['jobs'][0]
    
    # Read metrics
    read_iops = job['read']['iops']
    read_iops_std = job['read'].get('iops_stddev', 0.0)
    read_bw = job['read']['bw_bytes'] / (1024 * 1024)  # MB/s
    read_bw_std = job['read'].get('bw_dev', 0.0) / 1024.0  # MB/s
    read_lat = job['read']['lat_ns']['mean'] / 1000.0  # us
    read_lat_std = job['read']['lat_ns'].get('stddev', 0.0) / 1000.0  # us
    
    # Write metrics
    write_iops = job['write']['iops']
    write_iops_std = job['write'].get('iops_stddev', 0.0)
    write_bw = job['write']['bw_bytes'] / (1024 * 1024)  # MB/s
    write_bw_std = job['write'].get('bw_dev', 0.0) / 1024.0  # MB/s
    write_lat = job['write']['lat_ns']['mean'] / 1000.0  # us
    write_lat_std = job['write']['lat_ns'].get('stddev', 0.0) / 1000.0  # us
    
    return {
        'read': {
            'iops': read_iops, 'iops_std': read_iops_std,
            'bw': read_bw, 'bw_std': read_bw_std,
            'lat': read_lat, 'lat_std': read_lat_std
        },
        'write': {
            'iops': write_iops, 'iops_std': write_iops_std,
            'bw': write_bw, 'bw_std': write_bw_std,
            'lat': write_lat, 'lat_std': write_lat_std
        }
    }

def get_stats(vals):
    if not vals:
        return 0.0, 0.0
    mean = statistics.mean(vals)
    std = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return mean, std

def main():
    if len(sys.argv) < 3:
        print("Usage: parse_results.py <node_type> <results_dir>")
        sys.exit(1)
        
    node_type = sys.argv[1]
    results_dir = sys.argv[2]
    if not os.path.isdir(results_dir):
        print(f"Error: {results_dir} is not a directory.")
        sys.exit(1)
        
    workloads = [
        "randread_4k",
        "randwrite_4k",
        "randrw_70_30",
        "seqread_128k",
        "seqwrite_128k"
    ]
    
    summary_lines = []
    summary_lines.append("# NVMe FIO Benchmark Summary")
    summary_lines.append(f"Node Type: `{node_type}`")
    summary_lines.append(f"Directory: `{results_dir}`\n")
    summary_lines.append("| Workload | Metric | Run Count | Average | StdDev |")
    summary_lines.append("| :--- | :--- | :---: | :---: | :---: |")
    
    printable_data = {}
    
    for wl in workloads:
        pattern = os.path.join(results_dir, f"{wl}_run*.log")
        files = glob.glob(pattern)
        if not files:
            # Fallback to legacy format
            legacy_file = os.path.join(results_dir, f"{wl}.log")
            if os.path.exists(legacy_file):
                files = [legacy_file]
            else:
                continue
            
        runs_data = []
        for f in sorted(files):
            try:
                runs_data.append(parse_fio_file(f))
            except Exception as e:
                print(f"Warning: Failed to parse {f}: {e}")
                
        if not runs_data:
            continue
            
        printable_data[wl] = {}
        
        # Determine if we parse read, write, or both
        is_mixed = (wl == "randrw_70_30")
        is_write = (wl == "randwrite_4k" or wl == "seqwrite_128k")
        is_read = (wl == "randread_4k" or wl == "seqread_128k")
        
        if len(runs_data) == 1:
            # Single-run internal deviation
            run = runs_data[0]
            if is_mixed:
                metrics = [
                    ('Read IOPS', run['read']['iops'], run['read']['iops_std']),
                    ('Read Bandwidth (MB/s)', run['read']['bw'], run['read']['bw_std']),
                    ('Read Latency (us)', run['read']['lat'], run['read']['lat_std']),
                    ('Write IOPS', run['write']['iops'], run['write']['iops_std']),
                    ('Write Bandwidth (MB/s)', run['write']['bw'], run['write']['bw_std']),
                    ('Write Latency (us)', run['write']['lat'], run['write']['lat_std'])
                ]
            elif is_write:
                metrics = [
                    ('Write IOPS', run['write']['iops'], run['write']['iops_std']),
                    ('Write Bandwidth (MB/s)', run['write']['bw'], run['write']['bw_std']),
                    ('Write Latency (us)', run['write']['lat'], run['write']['lat_std'])
                ]
            else: # is_read
                metrics = [
                    ('Read IOPS', run['read']['iops'], run['read']['iops_std']),
                    ('Read Bandwidth (MB/s)', run['read']['bw'], run['read']['bw_std']),
                    ('Read Latency (us)', run['read']['lat'], run['read']['lat_std'])
                ]
            
            for name, mean, std in metrics:
                printable_data[wl][name] = (mean, std)
                summary_lines.append(f"| {wl} | {name} | 1 | {mean:.2f} | {std:.2f} |")
        else:
            # Multi-run standard deviation
            metrics = []
            if is_mixed:
                metrics = [
                    ('Read IOPS', [r['read']['iops'] for r in runs_data]),
                    ('Read Bandwidth (MB/s)', [r['read']['bw'] for r in runs_data]),
                    ('Read Latency (us)', [r['read']['lat'] for r in runs_data]),
                    ('Write IOPS', [r['write']['iops'] for r in runs_data]),
                    ('Write Bandwidth (MB/s)', [r['write']['bw'] for r in runs_data]),
                    ('Write Latency (us)', [r['write']['lat'] for r in runs_data])
                ]
            elif is_write:
                metrics = [
                    ('Write IOPS', [r['write']['iops'] for r in runs_data]),
                    ('Write Bandwidth (MB/s)', [r['write']['bw'] for r in runs_data]),
                    ('Write Latency (us)', [r['write']['lat'] for r in runs_data])
                ]
            else: # is_read
                metrics = [
                    ('Read IOPS', [r['read']['iops'] for r in runs_data]),
                    ('Read Bandwidth (MB/s)', [r['read']['bw'] for r in runs_data]),
                    ('Read Latency (us)', [r['read']['lat'] for r in runs_data])
                ]
                
            for name, vals in metrics:
                mean, std = get_stats(vals)
                printable_data[wl][name] = (mean, std)
                summary_lines.append(f"| {wl} | {name} | {len(vals)} | {mean:.2f} | {std:.2f} |")
            
    summary_text = "\n".join(summary_lines)
    print("\n" + summary_text + "\n")
    
    # Save summary to file in the results directory
    summary_path = os.path.join(results_dir, "summary.md")
    with open(summary_path, 'w') as f:
        f.write(summary_text)
    print(f"Summary saved to {summary_path}")
    
    # Save structured json for plotting convenience
    json_path = os.path.join(results_dir, "summary.json")
    with open(json_path, 'w') as f:
        json.dump(printable_data, f, indent=2)
    print(f"Structured data saved to {json_path}")

if __name__ == "__main__":
    main()
