#!/usr/bin/env python3
import os
import shutil
import random
import csv
import networkx as nx
import psutil
import subprocess

# Configuration - CHANGE THIS TO YOUR SSD PATH
OUTPUT_DIR = r"D:\eulerian_graph_testing"  # Example SSD path
NODE_SIZES = [100, 500, 1000, 2000, 5000]
CONSTANT_P = [0.05, 0.1, 0.15, 0.2]
SCALING_A = [0.1, 0.3, 0.5, 0.7]
TRIALS_PER_CONF = 5

def ensure_empty_dir(path):
    """Create or clear the output directory."""
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path)

def make_eulerian(G):
    """Modify graph to have exactly 0 or 2 odd-degree vertices."""
    odd = [n for n, d in G.degree() if d % 2 == 1]
    while len(odd) > 2:
        u, v = random.sample(odd, 2)
        if not G.has_edge(u, v):  # Avoid adding existing edges
            G.add_edge(u, v)
            odd.remove(u)
            odd.remove(v)
    return G

def generate_graph(n, p, seed):
    """Generate a connected G(n,p) graph and make it Eulerian."""
    random.seed(seed)
    G = nx.erdos_renyi_graph(n, p, seed=seed)
    G = nx.Graph(G)  # Ensure undirected
    
    # Force connectivity
    if not nx.is_connected(G):
        comps = sorted(nx.connected_components(G), key=len, reverse=True)
        main = comps[0]
        for comp in comps[1:]:
            u = random.choice(list(main))
            v = random.choice(list(comp))
            G.add_edge(u, v)
            main |= comp
    
    return make_eulerian(G)

def write_csvs(G, name, outdir):
    """Write nodes and edges to CSV files with SSD optimization."""
    # Node list
    node_path = os.path.join(outdir, f"nodes_{name}.csv")
    with open(node_path, "w", newline="", buffering=1024*1024) as f:  # 1MB buffer
        w = csv.writer(f)
        w.writerow(["id"])
        for n in sorted(G.nodes()):
            w.writerow([n])
    
    # Edge list
    edge_path = os.path.join(outdir, f"edges_{name}.csv")
    with open(edge_path, "w", newline="", buffering=1024*1024) as f:  # 1MB buffer
        w = csv.writer(f)
        w.writerow(["source", "target"])
        for u, v in G.edges():
            w.writerow([u, v])

def optimize_for_ssd(drive_letter):
    """Optimize SSD performance settings."""
    try:
        # Disable last access timestamp (Windows only)
        if os.name == 'nt':
            subprocess.run(f'fsutil behavior set disablelastaccess 1', shell=True, check=False)
            print(f"✓ Optimized SSD settings for drive {drive_letter}")
    except Exception as e:
        print(f"Note: Could not optimize SSD settings: {e}")

def main():
    # Ensure SSD path exists and is empty
    ensure_empty_dir(OUTPUT_DIR)
    
    # Optimize for SSD
    drive_letter = os.path.splitdrive(OUTPUT_DIR)[0]
    optimize_for_ssd(drive_letter)
    
    count = 0
    total_graphs = len(NODE_SIZES) * (len(CONSTANT_P) + len(SCALING_A)) * TRIALS_PER_CONF
    
    print(f"Generating {total_graphs} Eulerian graphs...")
    print(f"Output directory: {OUTPUT_DIR}")
    
    for i, n in enumerate(NODE_SIZES):
        print(f"\n🔷 Processing n={n} ({i+1}/{len(NODE_SIZES)})")
        
        # Constant probabilities
        for p in CONSTANT_P:
            for t in range(1, TRIALS_PER_CONF + 1):
                seed = n * 10000 + int(p * 1000) * 10 + t
                name = f"n{n}_const_{str(p).replace('.', '')}_t{t}"
                G = generate_graph(n, p, seed)
                write_csvs(G, name, OUTPUT_DIR)
                count += 1
                print(f"  Generated {name} ({count}/{total_graphs})")
        
        # Scaling probabilities
        for a in SCALING_A:
            p = n ** (-a)
            for t in range(1, TRIALS_PER_CONF + 1):
                seed = n * 20000 + int(a * 10) * 10 + t
                name = f"n{n}_scale_{str(a).replace('.', '')}_t{t}"
                G = generate_graph(n, p, seed)
                write_csvs(G, name, OUTPUT_DIR)
                count += 1
                print(f"  Generated {name} ({count}/{total_graphs})")
    
    print(f"\n✅ Generated {count} Eulerian graphs in '{OUTPUT_DIR}/'")

if __name__ == "__main__":
    main()