# Enterprise corpus validation

**Native validation is blocked.** No local baseline, synthetic video, ZIP inspection,
or matching imported payload is evidence of native generation or independent invocation.

Implemented scenarios: **15**. Cases: **96**.
Directory packs: **5**; business industries: **7**.
Local baselines ready: **true**.
Local media ready: **true**.
Local corpus ready: **true**.

## Scenario catalog

| Scenario | Industry | Workflow family | Baseline cases | Demo video | Native |
|---|---|---|---|---|---|
| [Logistics: POD and carrier charge review](cross-industry/logistics-pod-charge-review/HOW_TO.md) | logistics | delivery-evidence-and-charge-reconciliation | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Approved time and expense to client billing draft reconciliation](cross-industry/services-billing-draft-review/HOW_TO.md) | professional-services | approval-aware-billing-draft-reconciliation | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Maintenance readiness and resource-window conflict plan](cross-industry/utilities-maintenance-window-plan/HOW_TO.md) | energy-utilities | readiness-and-constrained-window-allocation | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Advisory fee billing reconciliation](financial-services/advisory-fee-reconciliation/HOW_TO.md) | financial-services | effective-dated-tiered-fee-recomputation | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [AP three-way invoice, PO, and receipt exception matching](financial-services/ap-three-way-match/HOW_TO.md) | financial-services | procurement-quantity-price-exception-matching | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Bank-statement-to-ledger reconciliation review packet](financial-services/bank-ledger-reconciliation/HOW_TO.md) | financial-services | evidence-constrained-bank-ledger-matching | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Cold-chain immunization inventory temperature-excursion review packet](health-life-sciences/cold-chain-excursion-review/HOW_TO.md) | health-life-sciences | time-series-inventory-exposure | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Site essential-document completeness and expiry review](health-life-sciences/site-essential-document-review/HOW_TO.md) | health-life-sciences | temporal-document-completeness | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Laboratory specimen accession and order reconciliation exception report](health-life-sciences/specimen-accession-reconciliation/HOW_TO.md) | health-life-sciences | order-accession-reconciliation | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [BOM material-readiness and kitting shortage review plan](manufacturing/bom-kitting-review/HOW_TO.md) | manufacturing | versioned-graph-expansion-and-shadow-allocation | 10/10 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Incoming-lot quality evidence and disposition review packet](manufacturing/incoming-quality-review/HOW_TO.md) | manufacturing | evidence-gating-and-review-routing | 5/5 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Supplier delivery performance and shortage expediting review queue](manufacturing/supplier-expediting-review/HOW_TO.md) | manufacturing | event-cohort-reconciliation-and-expediting | 7/7 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Store/SKU/date promotion price audit with exception review](retail/promotion-price-audit/HOW_TO.md) | retail | temporal-pricing-rule-audit | 10/10 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Original-order returns and refund proposal reconciliation](retail/returns-refund-reconciliation/HOW_TO.md) | retail | original-transaction-reconciliation | 10/10 | baseline_visualization_ready | creation blocked; install/invoke not run |
| [Store replenishment proposal with inventory and DC constraints](retail/store-replenishment-proposal/HOW_TO.md) | retail | constrained-inventory-allocation | 9/9 | baseline_visualization_ready | creation blocked; install/invoke not run |

## Coverage and evidence limits


Counts and exact/structural reuse signals are observed; business diversity, research quality and golden independence still require review.

Research URLs and rule provenance are supplied by sector authors. The offline tool
does not claim to have fetched those pages or independently reviewed their conclusions.
Goldens are author-declared independent derivations, locked before execution; local
integrity checks do not prove independent human review.

The machine-readable [catalog](catalog.json) separates documented rules, observed
baseline steps, local semantic comparison, media evidence, and native states per case.

## Native gate

Approved Computer Use tools and an unlocked accessible session must both be restored, then parent-coordinated authorization is required. Do not use substitute channels. Old N00 was last Publishing... with unknown outcome and Creator disabled; inspect real Installed state before any retry.

The pending matrix is [output/status.json](../output/status.json). No native ZIP is
produced by this pipeline. Actual native outputs must be supplied by the authorized
operator later; read-only imports retain declared versus locally observed provenance.
