#!/usr/bin/env python3
"""
neo4j_eulerian_checking.py

- Connects to Neo4j server at localhost:7687 with provided credentials
- Performs chunked import of nodes and relationships from CSV files
- Computes Eulerian properties client-side (consistent with Memgraph script)
- Measures import and check times
- Outputs results to CSV
- Adapted from Memgraph script for Neo4j 5.24.0 Enterprise
- Updated with batched database clear to avoid memory errors
"""
from urllib.parse import urlparse
import os
import csv
import time
import logging
import random
from pathlib import Path
from neo4j import GraphDatabase, exceptions as neo4j_exceptions

# ----------------------------
# Configuration (tweak here)
# ----------------------------
GRAPH_DIR = r"H:\projects\eulerian_graph_testing"
RESULTS_FILE = "neo4j_eulerian_csv.csv"

NODE_SIZES = [100, 500, 1000, 2000, 5000]
CONSTANT_P = [0.05, 0.1, 0.15, 0.2]
SCALING_A = [0.1, 0.3, 0.5, 0.7]
TRIALS_PER_CONF = 5

# Import tunables
BATCH_SIZE = 1000
MAX_CLEAR_RETRIES = 6
MAX_IMPORT_RETRIES = 4
BASE_BACKOFF = 0.25

# If True, import an undirected view by creating both directions for each undirected pair.
MAKE_BIDIRECTIONAL = True

# Whether to attempt creating an index on :V(id).
CREATE_INDEX_ON_ID = True

# Connection details
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "rishikesh"
NEO4J_DB = "neo4j"  # Default database

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

logger.info(f"Connecting to {NEO4J_URI} using database '{NEO4J_DB}'")

# ----------------------------
# Driver helper
# ----------------------------
def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

# ----------------------------
# File helpers
# ----------------------------
def load_edge_file_to_list(edge_file):
    rows = []
    with open(edge_file, 'r', newline='') as f:
        r = csv.reader(f)
        _ = next(r, None)  # skip header if present
        for row in r:
            if not row:
                continue
            try:
                u = int(row[0]); v = int(row[1])
                if u == v:
                    continue  # skip self-loops
                rows.append((u, v))
            except ValueError:
                continue
    return rows

def chunked(iterable, size):
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]

# ----------------------------
# DB helpers (clear) - Updated with batching to avoid OOM
# ----------------------------
def clear_db_with_retries(session, max_retries=MAX_CLEAR_RETRIES):
    attempt = 0
    BATCH_DELETE_SIZE = 1000  # Tune: reduce to 1000 if OOM persists, increase for speed
    while attempt < max_retries:
        attempt += 1
        deleted_total = 0
        while True:  # Loop until no more nodes to delete
            tx = session.begin_transaction()
            try:
                result = tx.run(
                    f"MATCH (n) WITH n LIMIT {BATCH_DELETE_SIZE} DETACH DELETE n RETURN count(*) AS deleted"
                )
                deleted = result.single()["deleted"]
                deleted_total += deleted
                tx.commit()
                if deleted == 0:
                    logger.info(f"Cleared {deleted_total} nodes in batches.")
                    return  # Database cleared successfully
            except neo4j_exceptions.TransientError as e:
                try:
                    tx.rollback()
                except Exception:
                    pass
                backoff = BASE_BACKOFF * (2 ** (attempt - 1))
                jitter = random.uniform(0, backoff * 0.3)
                sleep = backoff + jitter
                logger.warning(f"Clear DB attempt {attempt} transient error: {e}. Retrying in {sleep:.2f}s...")
                time.sleep(sleep)
                break  # Retry the batch loop
        if deleted_total > 0:
            logger.info(f"Partial clear: {deleted_total} nodes deleted so far.")
    logger.error("Failed to clear DB after max retries.")
    raise RuntimeError("Persistent error clearing DB")

# ----------------------------
# Chunked import (nodes + relationships)
# ----------------------------
def import_edges_in_chunks(session, original_edges, batch_size=BATCH_SIZE, max_retries=MAX_IMPORT_RETRIES,
                           create_index=CREATE_INDEX_ON_ID, make_bidirectional=MAKE_BIDIRECTIONAL):
    """
    - original_edges: list of (u, v) tuples
    - If make_bidirectional, deduplicate undirected pairs and create both directions.
    - Retries each chunk on TransientError.
    """
    # Prepare nodes
    node_ids = sorted({u for u, v in original_edges} | {v for u, v in original_edges})
    logger.info(f"Preparing import: {len(node_ids)} nodes, {len(original_edges)} raw edges")

    # Prepare relationships
    if make_bidirectional:
        undirected = set()
        for u, v in original_edges:
            a, b = min(u, v), max(u, v)
            undirected.add((a, b))
        rels_to_import = list(undirected)
        logger.info(f"MAKE_BIDIRECTIONAL=True -> {len(rels_to_import)} unique pairs")
    else:
        seen = set()
        rels_to_import = []
        for u, v in original_edges:
            if (u, v) not in seen:
                seen.add((u, v))
                rels_to_import.append((u, v))
        logger.info(f"MAKE_BIDIRECTIONAL=False -> {len(rels_to_import)} directed rels")

    # Create nodes
    node_create_query = "UNWIND $chunk AS id MERGE (n:V {id: id})"
    total_node_chunks = -(-len(node_ids) // batch_size)
    for idx, chunk in enumerate(chunked(node_ids, batch_size), 1):
        attempt = 0
        while True:
            attempt += 1
            tx = session.begin_transaction()
            try:
                tx.run(node_create_query, chunk=chunk)
                tx.commit()
                if idx % 10 == 0 or idx == total_node_chunks:
                    logger.info(f"Created node chunk {idx}/{total_node_chunks}")
                break
            except neo4j_exceptions.TransientError as e:
                tx.rollback()
                if attempt >= max_retries:
                    raise
                backoff = BASE_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, BASE_BACKOFF)
                logger.warning(f"Node chunk {idx} error: {e}. Retry in {backoff:.2f}s")
                time.sleep(backoff)

    # Create index
    if create_index:
        try:
            session.run("CREATE INDEX IF NOT EXISTS FOR (v:V) ON (v.id)")
            logger.info("Created index on :V(id).")
        except Exception as e:
            logger.warning(f"Index creation failed (continuing): {e}")

    # Create relationships - Updated to avoid Cartesian product warning
    rel_query_bidir = (
        "UNWIND $chunk AS r "
        "MATCH (a:V {id: r[0]}) "
        "WITH a, r "
        "MATCH (b:V {id: r[1]}) "
        "WITH a, b "
        "CREATE (a)-[:CONNECTED_TO]->(b), (b)-[:CONNECTED_TO]->(a)"
    )
    rel_query_dir = (
        "UNWIND $chunk AS r "
        "MATCH (a:V {id: r[0]}) "
        "WITH a, r "
        "MATCH (b:V {id: r[1]}) "
        "WITH a, b "
        "CREATE (a)-[:CONNECTED_TO]->(b)"
    )
    query = rel_query_bidir if make_bidirectional else rel_query_dir
    total_rel_chunks = -(-len(rels_to_import) // batch_size)
    for idx, chunk in enumerate(chunked(rels_to_import, batch_size), 1):
        attempt = 0
        while True:
            attempt += 1
            tx = session.begin_transaction()
            try:
                tx.run(query, chunk=chunk)
                tx.commit()
                if idx % 25 == 0 or idx == total_rel_chunks:
                    logger.info(f"Committed rel chunk {idx}/{total_rel_chunks}")
                break
            except neo4j_exceptions.TransientError as e:
                tx.rollback()
                if attempt >= max_retries:
                    raise
                backoff = BASE_BACKOFF * (2 ** (attempt - 1)) + random.uniform(0, BASE_BACKOFF)
                logger.warning(f"Rel chunk {idx} error: {e}. Retry in {backoff:.2f}s")
                time.sleep(backoff)

# ----------------------------
# Read helpers
# ----------------------------
def read_single(session, cypher, params=None):
    with session.begin_transaction() as tx:
        rec = tx.run(cypher, params or {}).single()
        return rec[0] if rec else None

Q_COUNT_NODES = "MATCH (n:V) RETURN count(n) AS cnt"
Q_COUNT_DIRECTED_EDGES = "MATCH ()-[:CONNECTED_TO]->() RETURN count(*) AS cnt"

# ----------------------------
# Client-side graph stats
# ----------------------------
def compute_graph_stats(edges_list):
    parent = {}
    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]
    def union(a, b):
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    deg = {}
    nodes = set()
    for u, v in edges_list:
        nodes.add(u)
        nodes.add(v)
        if u not in parent:
            parent[u] = u
        if v not in parent:
            parent[v] = v
        union(u, v)
        deg[u] = deg.get(u, 0) + 1
        deg[v] = deg.get(v, 0) + 1

    roots = {find(x) for x in nodes} if nodes else set()
    is_connected = len(roots) <= 1
    odd_count = sum(1 for d in deg.values() if d % 2 == 1)
    return {'nodes': len(nodes), 'edges': len(edges_list), 'odd_count': odd_count, 'is_connected': is_connected}

# ----------------------------
# Main experiment loop
# ----------------------------
def process_all():
    driver = get_driver()
    rows_out = []

    for n in NODE_SIZES:
        # constant-p
        for p in CONSTANT_P:
            p_str = str(p).replace('.', '')
            for t in range(1, TRIALS_PER_CONF + 1):
                trial_name = f"n{n}_const_{p_str}_t{t}"
                edge_file = os.path.join(GRAPH_DIR, f"edges_{trial_name}.csv")
                if not os.path.exists(edge_file):
                    logger.warning(f"Missing {trial_name}, skipping.")
                    continue
                logger.info(f"▶ Processing {trial_name}")

                edges_list = load_edge_file_to_list(edge_file)
                stats = compute_graph_stats(edges_list)

                with driver.session(database=NEO4J_DB) as session:
                    clear_db_with_retries(session)

                    import_start = time.perf_counter()
                    import_edges_in_chunks(session, edges_list)
                    import_time = time.perf_counter() - import_start

                    # Warm-up
                    session.run("MATCH (a:V)-[:CONNECTED_TO]->(b:V) RETURN count(*) LIMIT 1").consume()

                    for trial in range(TRIALS_PER_CONF + 1):
                        t_nodes_start = time.perf_counter()
                        nodes_count_db = read_single(session, Q_COUNT_NODES)
                        t_nodes = time.perf_counter() - t_nodes_start

                        t_edges_start = time.perf_counter()
                        directed_edges = read_single(session, Q_COUNT_DIRECTED_EDGES)
                        t_edges = time.perf_counter() - t_edges_start
                        edges_count_db = directed_edges // 2 if MAKE_BIDIRECTIONAL else directed_edges

                        nodes_count = stats['nodes']
                        edges_count = stats['edges']
                        odd_count = stats['odd_count']
                        is_connected = stats['is_connected']

                        check_time = round(t_nodes + t_edges, 6)
                        eulerian = is_connected and odd_count == 0
                        path_len = edges_count if eulerian else 0

                        rows_out.append([
                            trial_name,
                            n,
                            p,
                            trial,
                            round(import_time, 6),
                            check_time,
                            eulerian,
                            int(path_len),
                        ])
                        logger.info(f"✅ {trial_name} t{trial}: Eulerian={eulerian}, edges_db={edges_count_db}, edges_csv={edges_count}, check_time={check_time}s")

        # scaling-a
        for a in SCALING_A:
            a_str = str(a).replace('.', '')
            for t in range(1, TRIALS_PER_CONF + 1):
                trial_name = f"n{n}_scale_{a_str}_t{t}"
                edge_file = os.path.join(GRAPH_DIR, f"edges_{trial_name}.csv")
                if not os.path.exists(edge_file):
                    logger.warning(f"Missing {trial_name}, skipping.")
                    continue
                logger.info(f"▶ Processing {trial_name}")

                edges_list = load_edge_file_to_list(edge_file)
                stats = compute_graph_stats(edges_list)

                with driver.session(database=NEO4J_DB) as session:
                    clear_db_with_retries(session)

                    import_start = time.perf_counter()
                    import_edges_in_chunks(session, edges_list)
                    import_time = time.perf_counter() - import_start

                    # Warm-up
                    session.run("MATCH (a:V)-[:CONNECTED_TO]->(b:V) RETURN count(*) LIMIT 1").consume()

                    for trial in range(TRIALS_PER_CONF + 1):
                        t_nodes_start = time.perf_counter()
                        nodes_count_db = read_single(session, Q_COUNT_NODES)
                        t_nodes = time.perf_counter() - t_nodes_start

                        t_edges_start = time.perf_counter()
                        directed_edges = read_single(session, Q_COUNT_DIRECTED_EDGES)
                        t_edges = time.perf_counter() - t_edges_start
                        edges_count_db = directed_edges // 2 if MAKE_BIDIRECTIONAL else directed_edges

                        nodes_count = stats['nodes']
                        edges_count = stats['edges']
                        odd_count = stats['odd_count']
                        is_connected = stats['is_connected']

                        check_time = round(t_nodes + t_edges, 6)
                        eulerian = is_connected and odd_count == 0
                        path_len = edges_count if eulerian else 0

                        rows_out.append([
                            trial_name,
                            n,
                            a,
                            trial,
                            round(import_time, 6),
                            check_time,
                            eulerian,
                            int(path_len),
                        ])
                        logger.info(f"✅ {trial_name} t{trial}: Eulerian={eulerian}, edges_db={edges_count_db}, edges_csv={edges_count}, check_time={check_time}s")

    # Write results
    out_headers = ["name", "nodes", "p_or_a", "trial", "import_time", "check_time", "eulerian", "path_length"]
    with Path(RESULTS_FILE).open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(out_headers)
        w.writerows(rows_out)

    logger.info(f"\n📄 Results saved to {RESULTS_FILE}")

if __name__ == "__main__":
    process_all()