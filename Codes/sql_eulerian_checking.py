import sqlite3
import csv
import time
import os
import logging

# Configuration - matching your other scripts
GRAPH_DIR = r"H:\projects\eulerian_graph_testing"
RESULTS_FILE = "sql_eulerian_check_results.csv"
NODE_SIZES = [100, 500, 1000, 2000, 5000]
CONSTANT_P = [0.05, 0.1, 0.15, 0.2]
SCALING_A = [0.1, 0.3, 0.5, 0.7]
TRIALS_PER_CONF = 5

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# SQL Queries
CREATE_NODES_TABLE = """
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY
);
"""

CREATE_EDGES_TABLE = """
CREATE TABLE IF NOT EXISTS edges (
    source INTEGER,
    target INTEGER,
    FOREIGN KEY (source) REFERENCES nodes(id),
    FOREIGN KEY (target) REFERENCES nodes(id)
);
"""

# Index for faster queries
CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
"""

# Degrees: count odd degrees
CHECK_DEGREES = """
WITH degrees AS (
    SELECT node, COUNT(*) AS degree
    FROM (
        SELECT source AS node FROM edges
        UNION ALL
        SELECT target AS node FROM edges
    )
    GROUP BY node
)
SELECT COUNT(*) AS odd_count
FROM degrees
WHERE degree % 2 = 1;
"""

# Connectivity: recursive CTE from a starting node (min id)
CHECK_CONNECTED = """
WITH RECURSIVE connected(node) AS (
    SELECT MIN(id) FROM nodes
    UNION
    SELECT e.target FROM edges e JOIN connected c ON e.source = c.node
    UNION
    SELECT e.source FROM edges e JOIN connected c ON e.target = c.node
)
SELECT (SELECT COUNT(*) FROM nodes) = (SELECT COUNT(DISTINCT node) FROM connected) AS is_connected;
"""

# Edge count for path length
GET_EDGE_COUNT = """
SELECT COUNT(*) FROM edges;
"""

def run_tests():
    rows = []
    conn = sqlite3.connect(':memory:')  # In-memory DB for speed; use a file like 'test.db' if memory issues arise
    
    # Increase recursion limit if needed for large graphs
    conn.execute("PRAGMA recursive_triggers = ON;")
    # SQLite default recursion depth is 1000; for N=5000, may need higher
    conn.execute("PRAGMA recursive_depth = 10000;")  # Adjust if errors occur
    
    for n in NODE_SIZES:
        # Constant probability trials
        for p in CONSTANT_P:
            p_str = str(p).replace('.', '')
            for t in range(1, TRIALS_PER_CONF + 1):
                name = f"n{n}_const_{p_str}_t{t}"
                node_file = os.path.join(GRAPH_DIR, f"nodes_{name}.csv")
                edge_file = os.path.join(GRAPH_DIR, f"edges_{name}.csv")
                if not (os.path.exists(node_file) and os.path.exists(edge_file)):
                    logging.warning(f"Missing files for {name}, skipping.")
                    continue
                
                logging.info(f"▶ Processing {name}")
                
                # Reset tables
                conn.executescript("DROP TABLE IF EXISTS edges; DROP TABLE IF EXISTS nodes;")
                conn.executescript(CREATE_NODES_TABLE + CREATE_EDGES_TABLE + CREATE_INDEX)
                
                # Import time
                import_start = time.perf_counter()
                
                # Load nodes
                with open(node_file, 'r') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    nodes_data = [(int(row[0]),) for row in reader]
                conn.executemany("INSERT INTO nodes (id) VALUES (?)", nodes_data)
                
                # Load edges (assuming undirected multigraph, stored as is)
                with open(edge_file, 'r') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    edges_data = [(int(row[0]), int(row[1])) for row in reader]
                conn.executemany("INSERT INTO edges (source, target) VALUES (?, ?)", edges_data)
                
                conn.commit()
                import_time = time.perf_counter() - import_start
                
                # Check time
                check_start = time.perf_counter()
                
                cursor = conn.cursor()
                odd_count = cursor.execute(CHECK_DEGREES).fetchone()[0]
                is_connected = cursor.execute(CHECK_CONNECTED).fetchone()[0]
                path_len = cursor.execute(GET_EDGE_COUNT).fetchone()[0]  # Since Eulerian path length = num edges
                
                has_eulerian = bool(is_connected and odd_count in (0, 2))
                
                check_time = time.perf_counter() - check_start
                
                rows.append([name, n, p, t, round(import_time, 4), round(check_time, 4), has_eulerian, path_len])
                logging.info(f"✅ {name}: Eulerian={has_eulerian}, edges={path_len}, import_time={import_time:.4f}s, check_time={check_time:.4f}s")
        
        # Scaling probability trials
        for a in SCALING_A:
            a_str = str(a).replace('.', '')
            for t in range(1, TRIALS_PER_CONF + 1):
                name = f"n{n}_scale_{a_str}_t{t}"
                node_file = os.path.join(GRAPH_DIR, f"nodes_{name}.csv")
                edge_file = os.path.join(GRAPH_DIR, f"edges_{name}.csv")
                if not (os.path.exists(node_file) and os.path.exists(edge_file)):
                    logging.warning(f"Missing files for {name}, skipping.")
                    continue
                
                logging.info(f"▶ Processing {name}")
                
                # Reset tables
                conn.executescript("DROP TABLE IF EXISTS edges; DROP TABLE IF EXISTS nodes;")
                conn.executescript(CREATE_NODES_TABLE + CREATE_EDGES_TABLE + CREATE_INDEX)
                
                # Import time
                import_start = time.perf_counter()
                
                # Load nodes
                with open(node_file, 'r') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    nodes_data = [(int(row[0]),) for row in reader]
                conn.executemany("INSERT INTO nodes (id) VALUES (?)", nodes_data)
                
                # Load edges
                with open(edge_file, 'r') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    edges_data = [(int(row[0]), int(row[1])) for row in reader]
                conn.executemany("INSERT INTO edges (source, target) VALUES (?, ?)", edges_data)
                
                conn.commit()
                import_time = time.perf_counter() - import_start
                
                # Check time
                check_start = time.perf_counter()
                
                cursor = conn.cursor()
                odd_count = cursor.execute(CHECK_DEGREES).fetchone()[0]
                is_connected = cursor.execute(CHECK_CONNECTED).fetchone()[0]
                path_len = cursor.execute(GET_EDGE_COUNT).fetchone()[0]
                
                has_eulerian = bool(is_connected and odd_count in (0, 2))
                
                check_time = time.perf_counter() - check_start
                
                rows.append([name, n, a, t, round(import_time, 4), round(check_time, 4), has_eulerian, path_len])
                logging.info(f"✅ {name}: Eulerian={has_eulerian}, edges={path_len}, import_time={import_time:.4f}s, check_time={check_time:.4f}s")
    
    # Write results to CSV
    with open(RESULTS_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "nodes", "p_or_a", "trial", "import_time", "check_time", "eulerian", "path_length"])
        writer.writerows(rows)
    
    logging.info(f"\n📄 Results saved to {RESULTS_FILE}")

if __name__ == "__main__":
    run_tests()