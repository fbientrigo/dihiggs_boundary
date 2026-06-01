# Project Bootstrap — dihiggs_boundary

## Current goal

Build a clean, reproducible, modular 2HDM boundary/constraint atlas project.

The immediate goal is not MCMC and not a full paper-level likelihood.

The immediate goal is:

1. create a theory-only atlas using 2HDMC;
2. preserve all proposed points, including failed points;
3. classify rejection reasons;
4. generate first 2D maps of valid/invalid theory regions;
5. later enrich theory-valid points with HiggsTools.

## Current repo layout

Expected root:

    dihiggs_boundary/

Important directories:

    docs/
      model_contract.md
      atlas_schema.md
      concurrency_contract.md

    lib/
      2HDMC-1.8.0/
      higgstools-v1.2/

    dataset/
      hbdataset-v1.7/
      hsdataset-v1.1/

    configs/
      theory_atlas_v0.yaml

    cpp/
      include/dhb/
      src/
      apps/

    python/
      dihiggsbounds/

    llm_wiki/

    data/runs/

## Third-party policy

The directories below are read-only for agents:

    lib/2HDMC-1.8.0/**
    lib/higgstools-v1.2/**

Agents may inspect them and run documented build commands, but must not patch them without explicit human approval.

## Environment variables

Expected variables:

    DHB_ROOT
    DHB_2HDMC_ROOT
    DHB_HIGGSTOOLS_ROOT
    DHB_HB_DATASET_ROOT
    DHB_HS_DATASET_ROOT
    DHB_BUILD_ROOT
    DHB_RUNS_ROOT

The agent must verify all paths before using them.

## Physics contract summary

Baseline model:

    CP-conserving 2HDM
    Type-I Yukawa assignment
    mh = 125.09 GeV
    sin(beta-alpha) = 1.0
    mHp = mA
    lambda7 = 0.0
    lambda6 scanned, nonzero intended

Canonical input coordinates:

    mH
    mA
    tan_beta
    lambda6
    M

Derived:

    M2 = M * M
    m12_sq = M2 * sin(beta) * cos(beta)

Do not scan lambda1 as the primary coordinate in this project.

## Theory checks

The 2HDMC theory layer must evaluate:

    set_param_phys_ok
    positivity_ok
    unitarity_ok
    perturbativity_ok
    stability_ok

The canonical theory flag is:

    theory_ok =
      set_param_phys_ok
      && positivity_ok
      && unitarity_ok
      && perturbativity_ok
      && stability_ok

Each individual flag must be stored.

## Output principle

No point should disappear silently.

Every proposed point must produce one row with:

    input parameters
    derived parameters where available
    flags
    decays where available
    status
    rejection_stage
    rejection_reason

## Concurrency principle

Use process-level sharding first.

Do not write one shared CSV from multiple workers.

Safe pattern:

    input shard -> one worker process -> output shard

Then ingest shards into Parquet/DuckDB.

## Current development phase

Windows phase:

    prepare docs, config, folders, and agent instructions only.

WSL phase:

    inspect third-party docs
    build 2HDMC
    build HiggsTools
    build minimal C++ evaluator
    run smoke tests

## First deliverable after WSL build is available

A minimal evaluate_point executable or equivalent that evaluates one fixed point and emits a complete theory record.

Stop before implementing broad scans until single-point evaluation is validated.