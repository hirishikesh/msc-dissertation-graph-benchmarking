import os
import csv
import time
import logging
import argparse
from typing import Tuple
import networkx as nx
from neo4j import GraphDatabase, exceptions

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# Neo4j connection parameters
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "rishikesh"
NEO4J_DB = "neo4j"

# Output CSV for results
OUTPUT_CSV = "neo4j_eulerian_results.csv"

# Batch size for Neo4j imports
BATCH_SIZE = 1000

def connect_to_neo4j():
    """Create and return a Neo4j driver."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
        logging.info("Connected to Neo4j database.")
    except Exception as e:
        logging.error(f"Failed to connect to Neo4j: {e}")
        driver.close()
        raise
    return driver

def clear_database(driver):
    """Clear all nodes and relationships from the Neo4j database."""
    query = "MATCH (n) DETACH DELETE n"
    for attempt in range(3):
        try:
            with driver.session(database=NEO4J_DB) as session:
                session.run(query).consume()
            logging.info("Cleared existing data from database.")
            break
        except exceptions.Neo4jError as e:
            logging.warning(f"Transient error on clear (attempt {attempt+1}): {e}")
            time.sleep(1)
    else:
        logging.error("Failed to clear database after retries.")
        raise RuntimeError("Could not clear Neo4j database.")

def import_graph_neo4j(driver, nodes_file: str, edges_file: str) -> Tuple[int, int, float]:
    """Import nodes and edges from CSV files into Neo4j.
    Returns (node_count, edge_count, import_time_seconds)."""
    start_time = time.perf_counter()
    
    # Read nodes
    with open(nodes_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        nodes = [row for row in reader]
    node_count = len(nodes)
    logging.info(f"Nodes to import: {node_count}")

    # Import nodes in batches
    with driver.session(database=NEO4J_DB) as session:
        for i in range(0, node_count, BATCH_SIZE):
            batch = nodes[i:i+BATCH_SIZE]
            session.run("""
                UNWIND $batch AS row
                CREATE (n:Node {id: toInteger(row.id)})
            """, batch=batch)
    
    # Read edges
    with open(edges_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        edges = [row for row in reader]
    edge_count = len(edges)
    logging.info(f"Edges to import: {edge_count}")

    # Import edges in batches (creating bidirectional relationships)
    with driver.session(database=NEO4J_DB) as session:
        for i in range(0, edge_count, BATCH_SIZE):
            batch = edges[i:i+BATCH_SIZE]
            session.run("""
                UNWIND $batch AS row
                MATCH (a:Node {id: toInteger(row.source)}), (b:Node {id: toInteger(row.target)})
                CREATE (a)-[:CONNECTED_TO]->(b),
                       (b)-[:CONNECTED_TO]->(a)
            """, batch=batch)
    
    import_time = time.perf_counter() - start_time
    return node_count, edge_count, import_time

def check_eulerian_neo4j(driver) -> Tuple[bool, int, float]:
    """Check if the graph in Neo4j is Eulerian using Cypher queries.
    Returns (is_eulerian, edge_count, check_time_seconds)."""
    start_time = time.perf_counter()
    
    with driver.session(database=NEO4J_DB) as session:
        # Check if graph is connected using APOC
        connected_result = session.run("""
            MATCH (n:Node)
            WITH collect(n) as nodes
            CALL apoc.algo.unionFind(nodes) YIELD sets
            RETURN size(sets) = 1 as is_connected
        """)
        is_connected = connected_result.single()["is_connected"]
        
        # Check if all nodes have even degree
        even_degrees_result = session.run("""
            MATCH (n:Node)
            WITH n, size([(n)-[:CONNECTED_TO]-() | 1]) as degree
            RETURN all(degree % 2 = 0) as all_even_degrees
        """)
        all_even_degrees = even_degrees_result.single()["all_even_degrees"]
        
        # Count total edges (each edge stored twice, so divide by 2)
        edge_count_result = session.run("""
            MATCH ()-[r:CONNECTED_TO]->()
            RETURN count(r) / 2 as edge_count
        """)
        edge_count = edge_count_result.single()["edge_count"]
    
    check_time = time.perf_counter() - start_time
    is_eulerian = is_connected and all_even_degrees
    
    return is_eulerian, edge_count, check_time

def check_eulerian_networkx(nodes_file: str, edges_file: str) -> Tuple[bool, int, int, float]:
    """Check if the graph is Eulerian using NetworkX MultiGraph.
    Returns (is_eulerian, node_count, edge_count, check_time_seconds)."""
    start_time = time.perf_counter()
    
    # Create a MultiGraph
    G = nx.MultiGraph()
    
    # Read and add nodes
    with open(nodes_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            G.add_node(int(row['id']))
    
    node_count = G.number_of_nodes()
    logging.info(f"NetworkX: Nodes loaded: {node_count}")
    
    # Read and add edges
    with open(edges_file, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            G.add_edge(int(row['source']), int(row['target']))
    
    edge_count = G.number_of_edges()
    logging.info(f"NetworkX: Edges loaded: {edge_count}")
    
    # Check Eulerian properties
    is_connected = nx.is_connected(G) if G.number_of_nodes() > 0 else False
    all_even_degrees = all(degree % 2 == 0 for _, degree in G.degree())
    is_eulerian = is_connected and all_even_degrees
    
    check_time = time.perf_counter() - start_time
    return is_eulerian, node_count, edge_count, check_time

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Check if a graph is Eulerian using NetworkX and Neo4j.")
    parser.add_argument("nodes_file", help="Path to the nodes CSV file")
    parser.add_argument("edges_file", help="Path to the edges CSV file")
    args = parser.parse_args()
    
    # Validate file existence
    if not os.path.exists(args.nodes_file):
        logging.error(f"Nodes file not found: {args.nodes_file}")
        return
    if not os.path.exists(args.edges_file):
        logging.error(f"Edges file not found: {args.edges_file}")
        return
    
    # Extract graph name from nodes file
    graph_name = os.path.splitext(os.path.basename(args.nodes_file))[0].replace("nodes_", "")
    
    # Prepare output CSV
    write_header = not os.path.exists(OUTPUT_CSV)
    
    with open(OUTPUT_CSV, 'a', newline='', encoding='utf-8') as outf:
        writer = csv.writer(outf)
        if write_header:
            writer.writerow(["graph_name", "method", "node_count", "edge_count", "import_time_s", "euler_time_s", "is_eulerian"])
        
        try:
            # NetworkX Eulerian check
            logging.info(f"Processing graph '{graph_name}' with NetworkX")
            nx_is_eulerian, nx_node_count, nx_edge_count, nx_time = check_eulerian_networkx(args.nodes_file, args.edges_file)
            nx_status = "Yes" if nx_is_eulerian else "No"
            logging.info(f"NetworkX: Graph '{graph_name}': Eulerian path exists? {nx_status}")
            writer.writerow([graph_name, "NetworkX", nx_node_count, nx_edge_count, 0, f"{nx_time:.4f}", nx_status])
            outf.flush()
            
            # Neo4j Eulerian check
            logging.info(f"Processing graph '{graph_name}' with Neo4j")
            driver = connect_to_neo4j()
            try:
                clear_database(driver)
                node_count, edge_count, import_time = import_graph_neo4j(driver, args.nodes_file, args.edges_file)
                is_eulerian, edge_count_neo4j, euler_time = check_eulerian_neo4j(driver)
                status = "Yes" if is_eulerian else "No"
                logging.info(f"Neo4j: Graph '{graph_name}': Eulerian path exists? {status}")
                writer.writerow([graph_name, "Neo4j", node_count, edge_count, f"{import_time:.4f}", f"{euler_time:.4f}", status])
                outf.flush()
            finally:
                driver.close()
                
        except Exception as e:
            logging.error(f"Error processing graph '{graph_name}': {e}")

if __name__ == "__main__":
    main()