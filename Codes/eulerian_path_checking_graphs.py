import os
import csv
import time
import logging
import networkx as nx

# Configuration
GRAPH_DIR = r"H:\projects\eulerian_graph_testing"
RESULTS_FILE = "eulerian_check_results.csv"
NODE_SIZES = [100, 500, 1000, 2000, 5000]
CONSTANT_P = [0.05, 0.1, 0.15, 0.2]
SCALING_A = [0.1, 0.3, 0.5, 0.7]
TRIALS_PER_CONF = 5

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def load_multigraph_from_csv(edge_file):
    """Load edges from a CSV into a NetworkX MultiGraph."""
    G = nx.MultiGraph()
    with open(edge_file, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            u, v = map(int, row)
            G.add_edge(u, v)
    return G

def check_eulerian_path_with_networkx(G):
    """Check if the multigraph has an Eulerian circuit or path, return result and length."""
    if not nx.is_connected(G):
        return False, 0
    if nx.is_eulerian(G):
        path = list(nx.eulerian_circuit(G))
        return True, len(path)
    elif nx.has_eulerian_path(G):
        path = list(nx.eulerian_path(G))
        return True, len(path)
    return False, 0

def run_tests():
    rows = []
    for n in NODE_SIZES:
        # Constant probability trials
        for p in CONSTANT_P:
            p_str = str(p).replace('.', '')
            for t in range(1, TRIALS_PER_CONF + 1):
                name = f"n{n}_const_{p_str}_t{t}"
                edge_file = os.path.join(GRAPH_DIR, f"edges_{name}.csv")
                if not os.path.exists(edge_file):
                    logging.warning(f"Missing edges file for {name}, skipping.")
                    continue
                logging.info(f"▶ Processing {name}")

                start = time.perf_counter()
                G = load_multigraph_from_csv(edge_file)
                import_time = time.perf_counter() - start

                start = time.perf_counter()
                has_path, path_len = check_eulerian_path_with_networkx(G)
                check_time = time.perf_counter() - start

                rows.append([name, n, p, t,
                             round(import_time, 4), round(check_time, 4), has_path, path_len])
                logging.info(f"✅ {name}: Eulerian={has_path}, edges={G.number_of_edges()}")

        # Scaling probability trials
        for a in SCALING_A:
            a_str = str(a).replace('.', '')
            for t in range(1, TRIALS_PER_CONF + 1):
                name = f"n{n}_scale_{a_str}_t{t}"
                edge_file = os.path.join(GRAPH_DIR, f"edges_{name}.csv")
                if not os.path.exists(edge_file):
                    logging.warning(f"Missing edges file for {name}, skipping.")
                    continue
                logging.info(f"▶ Processing {name}")

                start = time.perf_counter()
                G = load_multigraph_from_csv(edge_file)
                import_time = time.perf_counter() - start

                start = time.perf_counter()
                has_path, path_len = check_eulerian_path_with_networkx(G)
                check_time = time.perf_counter() - start

                rows.append([name, n, a, t,
                             round(import_time, 4), round(check_time, 4), has_path, path_len])
                logging.info(f"✅ {name}: Eulerian={has_path}, edges={G.number_of_edges()}")

    # Write results
    with open(RESULTS_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "nodes", "p_or_a", "trial",
                         "import_time", "check_time", "eulerian", "path_length"])
        writer.writerows(rows)

    logging.info(f"\n📄 Results saved to {RESULTS_FILE}")

if __name__ == "__main__":
    run_tests()