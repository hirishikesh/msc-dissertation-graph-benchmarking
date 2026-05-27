# Dense Graphs, Fast Traversals: Benchmarking SQL vs Graph Engines at Scale

**MSc Artificial Intelligence Dissertation — University of Edinburgh, 2025**  
**Author:** Hirishikesh Parthasarathy | Supervised by Prof. Leonid Libkin  
**Grade:** Merit (2:1)

---

## Research Question

Which database engine — relational (SQL) or graph — delivers superior query performance for Eulerian path detection across graphs of varying density and scale? And how does performance change as graph size and edge density increase?

---

## Systems Benchmarked

| System | Type | Query Language |
|---|---|---|
| Neo4j | Graph database | Cypher / GQL |
| Memgraph | Graph database | Cypher |
| PostgreSQL | Relational database | SQL |
| DuckDB | Analytical SQL engine | SQL |
| NetworkX | Python graph library | Python API |

---

## Experimental Design

- **Node sizes:** 100, 500, 1,000, 2,000, 5,000 nodes
- **Density regimes:** Constant edge probability (p = 0.05, 0.10, 0.15, 0.20) and scaling density (a = 0.1, 0.3, 0.5, 0.7)
- **Trials per configuration:** 5 (for statistical reliability)
- **Total configurations:** 25+ density/size combinations
- **Statistical validation:** 95% confidence intervals on all reported results

---

## Repository Structure

```
├── src/
│   ├── graph_generation.py          # Random Eulerian graph generator
│   ├── eulerian_check_neo4j.py      # Neo4j benchmarking script
│   ├── eulerian_check_memgraph.py   # Memgraph benchmarking script
│   ├── eulerian_check_sql.py        # PostgreSQL / DuckDB benchmarking script
│   └── eulerian_path_networkx.py    # NetworkX baseline
├── results/
│   ├── eulerian_check_results.csv   # Aggregated benchmark results
│   ├── neo4j_results.csv            # Neo4j raw results
│   ├── memgraph_results.csv         # Memgraph raw results
│   └── sql_results.csv              # SQL engine raw results
├── queries/                         # Raw Cypher and SQL query files
├── docker/                          # Docker configuration for reproducibility
├── report/
│   └── dissertation.pdf             # Full dissertation report
├── requirements.txt
├── .gitignore
└── README.md
```

> **Note:** Raw graph CSV files (edge/node lists) are excluded from this repository due to size (~500MB+). Use `src/graph_generation.py` to regenerate them locally.

---

## How to Reproduce

### 1. Clone the repository
```bash
git clone https://github.com/hirishikesh/msc-dissertation-graph-benchmarking
cd msc-dissertation-graph-benchmarking
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Generate benchmark graphs
```bash
python src/graph_generation.py
```
This generates edge/node CSV files for all 25+ configurations in a local `data/` directory.

### 4. Run benchmarks
```bash
# Requires running Neo4j and Memgraph instances (see docker/ for setup)
python src/eulerian_check_neo4j.py
python src/eulerian_check_memgraph.py
python src/eulerian_check_sql.py
python src/eulerian_path_networkx.py
```

### 5. View results
Results are written to `results/`. Load `results/eulerian_check_results.csv` for the consolidated benchmark table.

---

## Key Findings

1. **PostgreSQL and DuckDB outperform graph databases** at low-to-medium density configurations for Eulerian path detection — the relational model handles degree-checking queries more efficiently than property graph traversal at this problem type.
2. **Neo4j and Memgraph scale better at high density** — as edge counts grow proportionally with node count, graph-native engines begin to close the performance gap.
3. **NetworkX serves as a reliable Python baseline** but does not scale beyond ~1,000 nodes without significant memory overhead.
4. **Statistical validation** at 95% CI confirms these findings are not artefacts of single-trial variance.

---

## Dependencies

```
networkx>=3.0
psycopg2>=2.9
neo4j>=5.0
pymgclient>=1.3
duckdb>=0.9
pandas>=2.0
numpy>=1.24
scipy>=1.10
psutil>=5.9
```

---

## Citation

If you use this work, please cite:

> Parthasarathy, H. (2025). *Dense Graphs, Fast Traversals: Benchmarking SQL vs Graph Engines at Scale*. MSc Dissertation, University of Edinburgh. Supervised by Prof. Leonid Libkin.

---

**Author:** Hirishikesh Parthasarathy  
[LinkedIn](https://linkedin.com/in/phirishikeshh) · [GitHub](https://github.com/hirishikesh)
