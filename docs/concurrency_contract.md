# Concurrency Contract — `dihiggsbounds`

## 1. Purpose

This document defines how `dihiggsbounds` may parallelize physics evaluations without risking silent corruption, nondeterminism, or thread-safety bugs.

The priority is:

```
correctness > debuggability > reproducibility > speed
```

A run that is 10–30% slower but reproducible is preferred over a faster run with unclear thread safety.

---

## 2. Core rule

The canonical unit of parallelism is a shard.

Each worker must receive one input shard and produce one output shard.

Workers must not write to a shared output file.

Recommended flow:

```
input points
  -> input shards
  -> independent worker processes
  -> output shards
  -> ingest
  -> Parquet / DuckDB
```

---

## 3. Process-first policy

The first production implementation must use process-level parallelism, not shared-memory threading.

Allowed:

```
Python runner starts N independent worker processes.
Each process executes the C++ shard evaluator.
Each process constructs its own 2HDMC objects.
Each process writes its own output file.
```

Not allowed in the initial implementation:

```
Multiple threads sharing one THDM object.
Multiple threads sharing one HiggsTools object.
Multiple threads writing to one CSV stream.
Global mutable physics state shared across workers.
```

Reason:

```
Process isolation avoids requiring proof that 2HDMC or HiggsTools are thread-safe.
```

---

## 4. Worker contract

Each worker must:

```
1. read exactly one input shard,
2. evaluate each point independently,
3. construct fresh physics objects per point or per safe local scope,
4. write exactly one output shard,
5. write one worker log,
6. exit with a meaningful return code.
```

A worker must not:

```
- modify third_party sources,
- write to global result files,
- depend on order of execution,
- depend on shared mutable counters for correctness,
- drop failed points silently.
```

---

## 5. 2HDMC object lifetime

The safe baseline is:

```
one THDM object per evaluated point
one SM object per evaluated point or immutable local worker setup
one Constraints object per evaluated point
one DecayTable object per evaluated point
```

This is conservative but debuggable.

Possible later optimization:

```
reuse immutable SM setup per worker
```

Only after reproducibility tests pass.

No global `THDM`, `Constraints`, or `DecayTable` objects are allowed in the MVP.

---

## 6. HiggsTools policy

HiggsTools must initially run as a separate enrichment stage.

Allowed MVP mode:

```
theory_ok points
  -> experimental enrichment shard
  -> one HiggsTools loader per process
  -> one output shard per process
```

Not allowed initially:

```
Online HiggsTools calls inside the main theory scan.
One shared HiggsTools object across multiple threads.
Mixed theory + experimental parallelism before theory-only reproducibility is established.
```

Reason:

```
HiggsTools dataset loading, caching, and internal state must be treated as not thread-safe until proven otherwise.
```

---

## 7. Output policy

### 7.1 No shared CSV

Workers must not append to a single shared CSV.

Bad:

```
worker_0 -> atlas.csv
worker_1 -> atlas.csv
worker_2 -> atlas.csv
```

Good:

```
worker_0 -> output/theory_000.csv
worker_1 -> output/theory_001.csv
worker_2 -> output/theory_002.csv
```

Then:

```
ingest output/*.csv -> atlas_theory.parquet
ingest output/*.csv -> atlas_theory.duckdb
```

### 7.2 Atomic output completion

A worker must write to a temporary file first:

```
theory_000.csv.tmp
```

and only rename to:

```
theory_000.csv
```

after successful completion.

This allows resume logic to distinguish completed shards from crashed shards.

### 7.3 Worker logs

Each worker must write:

```
logs/worker_000.stdout
logs/worker_000.stderr
logs/worker_000.manifest.json
```

The logs must include:

```
shard_id
input_path
output_path
n_points_input
n_points_written
start_time
end_time
elapsed_seconds
return_code
executable_path
config_hash
```

---

## 8. Determinism policy

The same input points must produce the same results independently of worker count.

Required comparison modes:

```
workers = 1
workers = 2
workers = 4
workers = 8
workers = 16, if practical
```

The comparison must sort by `point_id`.

Acceptable differences:

```
floating point differences within strict tolerance only if documented
```

Preferred for theory-only 2HDMC stage:

```
exact matching of flags
exact matching of rejection_stage
exact matching of rejection_reason
numerical matching within tolerance for floats
```

Recommended tolerance:

```
abs_tol = 1e-12 for ordinary derived values
rel_tol = 1e-10 for large/small floating values
```

Tolerances must be revisited after observing real output.

---

## 9. Ground truth mode

The canonical ground truth is:

```
workers = 1
threads_per_worker = 1
deterministic input order
fixed random seed
Debug or RelWithDebInfo build
```

Every new parallelization strategy must be compared against this mode.

---

## 10. Resume policy

A run is resumable at shard granularity.

A shard is complete only if all are true:

```
output shard exists
output shard is not empty
output shard has expected header
output shard row count matches expected point count
worker manifest exists
worker manifest return_code == 0
worker manifest n_points_written == n_points_input
```

If a completed shard exists and `--force` is not passed, it must be skipped.

If a `.tmp` file exists, it must be treated as incomplete.

---

## 11. Stop condition policy

Real-time stop conditions are allowed only at the scheduler level.

Example:

```
stop scheduling new shards after N candidate points are found
```

Not allowed:

```
killing workers mid-write as normal control flow
```

If early stopping is enabled:

```
- already running shards should finish,
- completed shards should remain valid,
- manifest must record early_stop_reason,
- manifest must record how many shards were skipped due to early stop.
```

---

## 12. Candidate detection

A candidate point may be detected in real time by the worker, but the worker must still write the full point result.

Allowed:

```
worker marks candidate_flag = true
worker writes candidate_score
runner reads shard summaries after completion
```

Optional later:

```
worker writes candidate event to a separate JSONL file
```

Not allowed initially:

```
shared live candidate database
shared mutable best-point object
global `g_bestBR`
non-atomic shared counters controlling physics results
```

---

## 13. Debugging policy

The project must provide small executables and modes suitable for debuggers.

Required executables or commands:

```
evaluate_point
evaluate_shard_theory
validate_shard
compare_runs
```

Required build modes:

```
Debug
RelWithDebInfo
Release
ASAN/UBSAN if supported
```

Recommended debugging commands:

```
gdb --args build/cpp/apps/evaluate_point tests/fixtures/point_valid.json

gdb --args build/cpp/apps/evaluate_shard_theory \
  --input tests/fixtures/shard_small.csv \
  --output scratch/debug_shard.csv
```

---

## 14. Third-party source policy

The following directories are read-only for agents:

```
third_party/2hdmc/**
third_party/higgstools/**
```

Allowed operations:

```
inspect read-only
run make or documented build commands
collect version metadata
clean build artifacts if explicitly requested
```

Forbidden operations without explicit human approval:

```
patching source files
changing headers
changing build scripts
committing changes inside third_party
mixing local modifications into physics results
```

If a third-party patch becomes necessary, it must be isolated in:

```
patches/
  2hdmc/
  higgstools/
```

and documented with:

```
reason
upstream version
exact diff
validation result
```

---

## 15. Environment policy

Every run must record:

```
hostname
OS
compiler
compiler version
build type
CPU model if available
worker count
threads per worker
OpenMP environment variables
LD_LIBRARY_PATH if relevant
2HDMC path
HiggsTools path if used
```

For process-sharded execution, each worker should set:

```
OMP_NUM_THREADS=1
```

unless explicitly testing OpenMP behavior.

---

## 16. Failure handling

A point-level failure must produce a row with:

```
status = error or theory_fail
rejection_stage
rejection_reason
error_message if available
```

A shard-level failure must produce:

```
nonzero worker return code
stderr log
incomplete or absent final output shard
worker manifest with failure status if possible
```

The runner must not silently ignore failed shards.

---

## 17. Scalability path

The intended path is:

```
Stage 1:
  workers=N processes
  threads_per_worker=1
  C++ theory evaluator
  CSV shards

Stage 2:
  workers=N processes
  HiggsTools enrichment
  output shards

Stage 3:
  optional internal threading inside each worker
  only after reproducibility tests

Stage 4:
  online combined theory+experiment evaluator
  only after HiggsTools reproducibility is proven
```

---

## 18. Required concurrency tests

### Test A — single-worker determinism

Run the same input twice:

```
run-theory --workers 1 --seed 123 --out run_a
run-theory --workers 1 --seed 123 --out run_b
```

Compare:

```
compare-runs run_a run_b --sort point_id
```

Must pass.

### Test B — parallel equivalence

Run:

```
run-theory --workers 1 --out run_single
run-theory --workers 8 --out run_parallel
```

Compare:

```
compare-runs run_single run_parallel --sort point_id
```

Must pass.

### Test C — resume

Run 20 shards.

Delete one completed output shard.

Rerun.

Expected:

```
19 shards skipped
1 shard recomputed
```

### Test D — crash safety

Create or simulate a `.tmp` output shard.

Rerun.

Expected:

```
tmp shard ignored or cleaned
shard recomputed
no false success
```

### Test E — stress

Run the same 1000-point fixture with:

```
workers = 1, 2, 4, 8, 16
```

All must match ground truth.

---

## 19. Acceptance criteria for concurrency MVP

Concurrency MVP is accepted only if:

```
1. workers=1 produces valid theory atlas.
2. workers=8 produces same results after sorting by point_id.
3. failed points are preserved.
4. no shared CSV is used.
5. each worker has independent output and logs.
6. resume works at shard level.
7. third_party directories remain unmodified.
8. all run metadata is recorded.
```

Speed is not an acceptance criterion until these pass.
