# DiHiggs boundary — June 2026 historical source note

Status: historical design/source note  
Original date: June 2026  
Promotion date: 2026-07-18  
Authority: current tracked implementation and contracts override this document

This note preserves useful implementation-aware context from the June 2026
boundary work. It is historical context, not a current scientific or
operational contract. The original source note and related audits are retained
in the external migration archive
`legacy_archive_2026-07-18/`; they are not required runtime inputs.

## Current tracked context

`dihiggs_boundary` is contract-aligned with the maintained `dihiggs` model
conventions, but it is not directly integrated with canonical
`dihiggs.point.v2` output. It retains some duplicated model-construction logic.
The current boundary model and evaluator contracts are maintained in
[`../model_contract.md`](../model_contract.md) and
[`../evaluate_point_contract.md`](../evaluate_point_contract.md). The golden
characterization of existing `evaluate_point` behavior is recorded in
[`../characterization_evaluate_point.md`](../characterization_evaluate_point.md)
and its tracked fixture manifest.

The current repository provides a theory evaluator, CSV contracts, optional
HB/HS enrichment, and atlas classification stages. Its golden tests
characterize the existing evaluator; they do not establish global physical
boundaries. Optional HB/HS execution requires external HiggsTools and dataset
installations that are not supplied by Git.

## Historical design reasoning

The June work separated three concerns:

1. a theory-stage evaluator that preserves one output row per attempted point,
   including construction and theory failures;
2. an optional experimental-enrichment stage for HiggsBounds/HiggsSignals;
3. an atlas stage that assigns explicit region classes and non-authoritative
   candidate tags for downstream investigation.

That separation remains useful because it keeps missing external tools distinct
from theory failure and makes CSV outputs auditable. It also motivated keeping
individual predicates, input coordinates, derived coordinates, and failure
reasons rather than collapsing all outcomes into one acceptance flag.

The historical work discussed fixed Type-I Yukawa settings, exact alignment,
`mHp=mA`, nonzero `lambda6`, and `lambda7=0` as a bounded model context. It
also highlighted the need to keep the M² convention explicit:

```text
M² = m12_sq / (sin(beta) * cos(beta))
m12_sq = M² * sin(beta) * cos(beta)
```

Those conventions are subject to the current tracked contracts. They do not
turn a local evaluator or a bounded scan into a global boundary result.

## Historical non-claims and unresolved items

The June note did not establish LHC limits, a global M² boundary, an LLP
benchmark, experimental exclusion, or validated acceptance beyond the
repository's theory predicates. Historical LHS campaigns, STU diagnostics,
HB/HS plans, and exploratory lambda1/M² relationships remain historical or
optional context unless revalidated under current contracts.

In particular, the following require a separate scientific decision before
promotion: validation of M² intervals against dense rectangular grids, the
mapping of `m_phi` to the current mass naming near 125 GeV, whether STU or
HB/HS should ever become production gates, and whether continuation heuristics
are physically meaningful beyond bounded search guidance.

Do not cite this note as authority for those claims. Use the current tracked
contracts, executable tests, and explicitly versioned outputs instead.
