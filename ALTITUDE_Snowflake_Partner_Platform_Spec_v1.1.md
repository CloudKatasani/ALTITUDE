# ALTITUDE — AI-Accelerated Snowflake Implementation, Migration & Run Partner

**Product Blueprint, Service Catalog & Build Specification — v1.1**

*October 2026 · Snowflake-native · Rubrics, mappings and known issues stored as data · Human approval before promotion*

> **Naming note.** `ALTITUDE` is a working codename. Every user-facing name is a theme token (`PRODUCT_NAME`, `COMPANY_NAME`) so the platform can be white-labelled for SI/Big-4 channel partners by configuration only. Avoid "Snow"/"Flake" in the final brand — Snowflake's trademark guidelines restrict partner use of its marks in company and product names, and the restriction will surface at partner-program review.

> **What changed in v1.1 (consulting review).** The value proposition is repositioned from "AI-accelerated migration" (now table stakes) to an **evidence-first** Snowflake partner. The go-to-market beachhead moves to existing Snowflake estates, through two new flagship packages: **Package D — Platform Deep Diagnostics** and **Package O — Platform Observability (add-on)**. New sections cover the honest differentiators, why to choose ALTITUDE (and when not to), an offer ladder with unit economics, outcome-backed commercials, and a specific IP clean-room requirement. Full review findings are in Appendix F.

---

## Contents

**Part I — Strategy**
1. Executive Summary
2. Experience Model — How Clients Work with ALTITUDE
3. Market, Problem & Positioning
4. Competitive Landscape, Differentiators & Why ALTITUDE
5. Business Model, Offer Ladder & Unit Economics

**Part II — Flagship Entry Packages**
6. Package D — Platform Deep Diagnostics
7. Package O — Platform Observability (Add-on)

**Part III — Migration Engine**
8. Migration Patterns (Lift-and-Shift, Re-platform, Re-architect, Greenfield, Hybrid, Open-Lakehouse)
9. Migration Lifecycle & Factory Method
10. Source Modules — Teradata, Oracle, SQL Server, Netezza, Redshift, Hadoop/Spark, Databricks, BigQuery, DB2/Mainframe, SAP, Greenplum/Vertica/Sybase, OLTP
11. ETL, Orchestration & BI Migration
12. Data Movement, CDC & Validation
13. Cutover, Coexistence & Decommissioning

**Part IV — Snowflake Implementation Excellence**
14. Snowflake Well-Architected Baseline (Best Practices)
15. Greenfield Implementation Blueprint

**Part V — AI Acceleration & Agents**
16. AI Across the Lifecycle
17. The AI Delivery Partner ("Sherpa") & Specialist Advisors
18. Agentic Run-Operations Fleet (Maintenance Agents)
19. AI-Ready Platform Module

**Part VI — Adjacent Service Streams**
20. Stream Prioritization
21. Data Governance · 22. Data Quality · 23. Observability · 24. FinOps · 25. Security · 26. Metadata, Semantic Layer & Data Products · 27. MDM, Sharing, Clean Rooms & Native Apps · 28. DataOps & Change Management

**Part VII — Platform Engineering**
29. Reference Architecture
30. Canonical Data Model
31. Knowledge Base as Data (Pattern Library)
32. Estimation Engine
33. Security, Tenancy & Compliance of the Platform Itself

**Part VIII — Commercial & Startup Plan**
34. Service Catalog & Pricing Shapes
35. Go-to-Market & Snowflake Partnership
36. Company Build Plan (0–24 months)
37. Risks & Mitigations
38. Build Plan for Claude Code (BUILD.md milestones)

**Appendices** — A. Known-Issues Register (YAML) · B. Assessment Questionnaire · C. Readiness Gates · D. First 90 Days (Founder Checklist) · E. Glossary · F. v1.1 Consulting Review & Change Log

---

# PART I — STRATEGY

## 1. Executive Summary

**The thesis in one line.** ALTITUDE is a senior, evidence-first Snowflake partner. It *diagnoses* an estate down to the dollar, *fixes* what costs money or creates risk, *keeps it observable*, and *migrates or modernises* with AI-accelerated delivery that is provably equivalent. It sells fixed-scope packages with outcome-backed commercials.

**The market reality: why the obvious pitch fails.** "AI-accelerated migration with accelerators" is now table stakes:
- Snowflake gives away **SnowConvert AI** for code conversion.
- In June 2026 Snowflake published its **Well-Architected Framework (WAF)**, with a free Cortex Code assessment skill.
- Elite partners already sell fixed-fee, AI-native delivery. phData has its Toolkit and the Forge methodology. Hakkoda (IBM) sells AI-accelerated migrations and BI modernisation.

A new entrant cannot win on certification counts, headcount or the generic "AI + accelerators" claim. It can win on five things:
- **depth of evidence**
- **breadth of diagnosis**, covering the warehouse *and* the BI/consumption layer
- **client-owned observability**
- **outcome-backed commercials**
- **regulated-industry depth**

**The entry strategy (tuned in v1.1).** Start where the sales cycle is shortest and the founder's ground is strongest: existing Snowflake customers. Multi-year migrations come later, because they need references the startup does not yet have.

```
Diagnose ──▶ Fix ──▶ Observe ──▶ Operate ──▶ Modernise / Migrate ──▶ AI-Ready
Package D   Sprints   Package O   Managed Run   Migration Factory      AI programme
```

1. **Package D — Platform Deep Diagnostics** (Section 6). A 2–6 week diagnostic of a Snowflake estate. It is metadata-only and evidence-backed, covers 10 domains, and produces quantified, prioritised suggestions with remediation-as-code. The fee is credited against follow-on work.
2. **Package O — Platform Observability, add-on** (Section 7). Turns the point-in-time diagnostic into a living scorecard: a multi-account telemetry archive, an ~80-KPI catalogue, chargeback, anomaly alerts and a "talk to your platform" agent. It runs in the client's own account and earns recurring revenue from month one.
3. **Follow-on work.** Remediation sprints, the managed run service, migrations and AI-readiness all reuse the same evidence store, Pattern Library and agent fleet.

**What ALTITUDE is made of**
1. **A platform** that orchestrates the lifecycle: diagnose → assess → plan → convert → move → validate → cut over → operate → make AI-ready. It wraps best-in-class tools (SnowConvert AI, Cortex Code, dbt, Openflow, CDC vendors) rather than competing with them.
2. **A codified knowledge base.** Mappings, known issues, diagnostic checks, estimation factors and gates are stored as versioned data.
3. **A senior services firm** selling fixed-scope packages, with the platform as its margin engine.
4. **A run business.** Observability plus an agentic maintenance fleet turn projects into recurring revenue.

**Why now**
- Code conversion is free, so value moves to diagnosis, validation, de-risking and operation.
- Snowflake's WAF gives buyers a shared vocabulary for platform health. ALTITUDE extends it rather than inventing its own.
- Cortex and Snowflake Intelligence put executive pressure on teams to be "AI-ready", and most estates are not.
- Agents can now handle the long tail of migration and operations work under human approval.

**Design principles (non-negotiable, CI-enforced)**

| # | Principle | Enforcement |
|---|---|---|
| 1 | Everything scored, mapped or estimated is stored as data | Mappings, known issues, rubrics, estimation factors live in versioned YAML → tables. CI fails on numeric thresholds in app code. |
| 2 | Metadata-only by default | Assessment harvests catalogs, query history, DDL and code. Row-level access only in the separately-gated validation module, per-dataset authorised and logged. |
| 3 | Every AI inference carries confidence + rationale | Below 0.80 → human review queue before it affects code, scores or estimates. |
| 4 | Human approval before promotion | No converted object, pipeline, grant or agent action reaches production without a recorded approver. |
| 5 | Immutable, keyed snapshots | Assessments, conversion runs, validation runs and cutover decisions are append-only snapshots — replayable for audit. |
| 6 | Source is never modified | Read-only connectors with published permission manifests; CI "kill test" proves no write path to source or target production. |
| 7 | Classification propagates mechanically | PII tags discovered at source flow to Snowflake tags → masking policies → pipeline contracts → agent scopes. |
| 8 | Tool-neutral source of truth | Generated SQL/dbt/Terraform are renderings, header-stamped `AUTO-GENERATED — DO NOT EDIT`. |
| 9 | Snowflake-native where possible | Platform core deployable inside the client's account (Native App / Snowpark Container Services) — the strongest security-review story. |
| 10 | Every suggestion is quantified and traceable | Each finding carries evidence IDs, a $ or risk value with its method, effort, confidence and rollback — or it is not published. |

---

## 2. Experience Model — How Clients Work with ALTITUDE

ALTITUDE is designed around five experience principles:
- **a guided path to an outcome**
- **an opinionated AI delivery partner**
- **specialist advisors**
- **executable skills**
- **capabilities available in whatever AI tool the client already uses**

The client should never face a blank page. At every stage the platform tells them where they are, what to do next and why.

| Experience capability | What it means for a Snowflake client |
|---|---|
| **Guided outcome path** | Diagnose → Fix → Observe → Operate → Migrate → AI-Ready, with the current phase, its gate criteria and the next three actions always visible |
| **Choose your route** | **Pattern and wave recommender**: lift-and-shift, re-platform, re-architect, greenfield, hybrid or open-lakehouse, scored against the harvested estate, constraints, budget and deadline |
| **Opinionated AI delivery partner** | **Sherpa**: a delivery co-pilot that challenges risky choices, e.g. "lift-and-shifting 4,200 BTEQ scripts with no test harness will blow your cutover date — here's why" |
| **Specialist advisors** | Teradata, Oracle PL/SQL, SSIS, FinOps, Security, Governance and Cortex advisors, each grounded in the Pattern Library and able to walk the user through a task step by step |
| **Multi-perspective decision review** | **Architecture Review Board**: one decision evaluated through CFO, CISO, Platform Architect, Data Steward, Delivery Lead, Business Owner and Snowflake Account Team lenses, giving one recommendation with dissent recorded |
| **Executable skills** | Run a diagnostic, convert a module, generate tests, reconcile a table, draft an SOW, produce a board pack |
| **Institutional knowledge** | **Pattern Library**: mappings, known issues, diagnostic checks, estimation factors and client-specific decisions, all stored as data |
| **Progress tracking** | **Progress boards**: suggestions identified vs realised, objects converted, validated and cut over, burn-down vs plan, decommission savings realised |
| **Buying-signal intelligence** (for ALTITUDE's own go-to-market) | Contract-renewal windows for Teradata, Oracle and Netezza; job postings for migration roles; Snowflake account-team referrals |
| **Live dashboards** | Over the engagement snapshot and the run estate (Package O) |
| **Available everywhere** | **ALTITUDE MCP server**: Claude, Cursor, Cortex Code and Copilot can call the diagnostic, conversion, validation and Pattern Library tools |

ALTITUDE therefore has **two faces**:
- **A client-facing delivery platform**, which is the main source of revenue.
- **A partner-enablement edition, later**, which lets small SIs and independent consultants run accelerated diagnostics and migrations under their own brand. White-label tokens make this a configuration exercise.

---

## 3. Market, Problem & Positioning

### 3.1 Problems Clients Actually Have

| Problem | Symptom | Cost |
|---|---|---|
| **Unknown estate** | Nobody knows how many of the 38,000 objects are used; 30–60% are typically dead | Migrating dead code inflates scope and timeline 1.5–2× |
| **Conversion ≠ migration** | Tools convert SQL; they do not migrate ETL behaviour, schedules, security, BI semantics, SLAs, or operational knowledge | "90% converted" programmes that are 40% done |
| **Silent semantic drift** | Case sensitivity, NULL vs empty string, numeric scale, date/time-zone, `SET`-table dedupe — code runs but answers differ | Business loses trust at UAT; parallel run extends by months |
| **Validation theatre** | Row counts match, aggregates don't; no row-level reconciliation for critical tables | Defects found post-cutover by finance |
| **Cost shock** | Warehouses sized like the old appliance, no auto-suspend discipline, no resource monitors | First Snowflake bill 2–3× forecast; executive backlash |
| **Lift-and-shift debt** | Legacy patterns (row-by-row procs, nightly full reloads) replicated on Snowflake | Pays cloud prices for appliance-era design |
| **Not AI-ready** | No semantic models, no descriptions, no classification, no lineage | Cortex/agent initiatives stall at security review |
| **No run model** | Migration team leaves; nobody owns cost, quality, access hygiene or Snowflake behaviour-change bundles | Degradation within two quarters |

### 3.2 Positioning Statement

*For data and platform leaders running — or moving to — Snowflake, ALTITUDE is the evidence-first Snowflake partner. We diagnose your estate down to the dollar, fix what matters, keep it observable in your own account, and migrate with proof that every answer still matches. Unlike conversion tools, we migrate the whole operating system of the warehouse, including BI and operations. Unlike large SIs, every recommendation and cutover decision traces back to evidence, and our fees are tied to outcomes.*

> Speed claims (e.g. "30–50% faster") are **targets**, not marketing copy, until they have been measured on the first 3–5 engagements and published with the method (calibration, Section 32).

### 3.3 Target Segments

| Segment | Trigger | Offer entry point |
|---|---|---|
| Mid-market ($200M–$2B revenue) on SQL Server / Oracle | Hardware refresh, licence renewal, cloud mandate | Fixed-price "Migration Sprint" |
| Enterprise on Teradata / Netezza / Exadata | Contract renewal 12–24 months out | Paid assessment → migration factory |
| Hadoop / Cloudera estates | Support cost, skills scarcity | Re-architect to Snowflake + Iceberg |
| Existing Snowflake customers (largest, fastest market) | Cost overrun, governance gaps, AI ambition | Well-Architected review, FinOps, AI-Ready, managed service |
| Regulated (utilities, banking, healthcare, insurance) | Audit findings, AI governance pressure | Governance + AI-readiness + run service |

> **Founder advantage to exploit:** deep utilities/energy (AMI, OT/IT, NERC/FERC) and Snowflake Observability/FinOps depth. Lead with a vertical — "Snowflake for regulated utilities" — rather than horizontal "we do migrations". Vertical focus is what makes a services startup referenceable within 12 months.

**Beachhead sequence (v1.1):**
1. Existing Snowflake customers in regulated industries, utilities first, through Packages D and O.
2. Mid-market SQL Server and Oracle migrations.
3. Enterprise Teradata and Netezza migration factories, once references exist.

---

## 4. Competitive Landscape, Differentiators & Why ALTITUDE

### 4.1 Landscape (Updated October 2026)

| Category | Examples | What they do well | Gap ALTITUDE exploits |
|---|---|---|---|
| **Snowflake first-party** | SnowConvert AI; Snowpark Migration Accelerator; Well-Architected Framework with a Cortex Code WAF assessment skill and Blueprint Manager; Snowflake Professional Services | Free AI-assisted conversion, with growing data-migration and validation coverage. Free control-level health assessment. Deep product knowledge | Does not run the programme, migrate ETL, BI and operations end-to-end, or put a dollar value on findings. Does not look at the BI layer, own cutover, or operate the estate afterwards |
| **Elite Snowflake SIs** | phData: 2026 Implementation Partner of the Year (seventh consecutive year) and 2026 AI Partner of the Year; Toolkit; Forge AI-native methodology; fixed-fee Cortex Code migrations; free security assessment. Hakkoda (IBM): AI-accelerated migrations, BI modernisation, Snowflake optimisation, Legacy Migration Accelerated Partner. Also Slalom, InterWorks, Evolv, Kipi.ai | Certifications at scale, many references, strong Snowflake relationships, fixed-fee AI offers | Horizontal positioning. Diagnostic outputs are rarely tied to an auditable evidence store. BI rationalisation and KPI lineage are usually separate engagements. Observability is usually a dashboard pack, not a data product the client owns |
| **Commercial conversion tools** | Next Pathway, Impetus LeapLogic, Datometry, Hexaware Amaze | Broad source coverage and ETL conversion | Licence cost; still conversion-centric |
| **Global SIs / Big 4** | Large multi-practice firms | Scale, relationships, multi-country programmes | Expensive, pyramid staffing, accelerators that vary by team |
| **Observability and FinOps SaaS** | Select, Keebo, Sundeck, Monte Carlo, Metaplane, Bigeye | Strong point solutions | Point tools that often copy telemetry out of the account and are often priced against spend; no delivery |

> Facts about named competitors come from their public materials as of October 2026. Re-verify them before any client-facing use.

### 4.2 The Honest Test: Table Stakes vs Real Differentiators

A differentiator is only real if a buyer can **verify it in the first meeting** and a large competitor would find it **awkward to copy**.

| Claim | Verdict | Why |
|---|---|---|
| "AI-accelerated migration" | **Table stakes** | SnowConvert AI is free; phData Forge and Hakkoda already market it |
| "Fixed-fee offers" | **Table stakes** | Elite partners already sell fixed-fee migrations |
| "Accelerators / toolkit" | **Table stakes** | Every Elite partner has one |
| "Free health check / WAF scan" | **Commoditised** | Snowflake's own WAF skill is free |
| "Certified engineers" | **Table stakes; ALTITUDE loses on count** | Leaders report 280+ certifications |
| Evidence-linked, dollar-quantified diagnostics that can be reproduced from a snapshot | **Differentiator** | Requires an evidence data model and discipline that people-led firms rarely build |
| Diagnosis that spans the warehouse *and* the BI/consumption layer (report rationalisation, KPI-to-column lineage) | **Differentiator** | The founder has proven the patterns on an estate of 60K+ reports. Most Snowflake partners stop at the warehouse |
| Observability delivered as a client-owned data product inside the account | **Differentiator** | Flat pricing by spend band, so ALTITUDE earns nothing extra when spend rises |
| Semantic-drift equivalence engine with auditor-grade evidence | **Differentiator** | Compounds with every engagement |
| Outcome-backed commercials (fee credit, value floor, re-baseline) | **Differentiator for a startup** | Large SIs rarely accept them |
| Least-privilege, in-account, metadata-only operation (no ACCOUNTADMIN, no row data) | **Differentiator** | Clears security review faster than tools that need admin rights or export data |
| Regulated-utility depth (NERC CIP-aligned access evidence, AMI-scale data, OT/IT boundary) | **Differentiator** | Hard to replicate horizontally |

### 4.3 The Eight Differentiators

| # | Differentiator | What the client gets | First-meeting proof | Defensibility |
|---|---|---|---|---|
| 1 | **Evidence-first, down to the dollar** | Every finding carries evidence IDs, a dollar or risk value with its method, effort, confidence and the fix. The same snapshot always gives the same result | A live D0 Snapshot run on the client's account with a read-only role, plus a sample findings register | Medium: copyable in principle, but it needs the data model, rubrics and discipline |
| 2 | **Whole-stack diagnosis: warehouse + pipelines + BI + AI** | Duplicate reports and conflicting KPI definitions found, dashboards whose refresh cost exceeds their use, KPI lineage down to source column | An anonymised case pattern from a 60K+ report estate, used only with employer and client permission, plus a rationalisation demo on synthetic data | Medium–High |
| 3 | **Observability the client owns** | A multi-account archive that keeps history beyond the native 365-day `ACCOUNT_USAGE` window, ~80 KPIs, chargeback, alerts and a Snowflake Intelligence agent, all running in the client's account | A demo deployment and the KPI catalogue | Medium |
| 4 | **Provable equivalence** | L0–L5 validation, drift detectors, mismatch clustering and go/no-go evidence packs (Section 12) | The open-source drift checker run on a sample of client SQL | Medium–High, and it compounds |
| 5 | **Fees tied to outcomes** | Fee credit, a value floor and free re-baselining (Section 6.8); flat pricing for observability | Contract terms in the proposal | Easy to copy on paper; culturally resisted by large SIs |
| 6 | **In-account, least privilege, metadata-only** | Uses `SNOWFLAKE` database roles rather than ACCOUNTADMIN. Row data never leaves. A Native App option is available | The permission manifest and bootstrap script handed over in the first meeting | Medium |
| 7 | **Agents that operate, under governance** | Autonomy levels L0–L3, approval workflow and immutable action audit, aligned to WAF guidance for agents | The agent-action audit table and an approval flow demo | Low–Medium (everyone will build agents; governance is the edge) |
| 8 | **Regulated-utility depth** | Access evidence aligned to NERC CIP, AMI-scale data patterns, OT/IT boundary design, regulatory reporting packs | Founder credentials and vertical use-case packs (Section 19.3) | High |

Delivery-model attribute (not a standalone differentiator): **senior-only teams with Big-4 rigour at boutique speed.** It adds credibility but limits capacity, so it has to be priced in.

### 4.4 Why Choose ALTITUDE (Client-Facing)

**Elevator pitch (30 seconds).** *"Most Snowflake partners will tell you what they think is wrong. We show you, with evidence from your own account, exactly where every dollar and every risk sits, including in the reports and KPIs your business relies on. Then we fix it, keep it observable in your own account, and stake part of our fee on the result."*

| # | Reason, in the buyer's language | What stands behind it |
|---|---|---|
| 1 | "You'll know exactly where every dollar and risk is, with evidence you can audit." | Package D suggestion engine; reproducible snapshots |
| 2 | "We look past the warehouse, at the reports and KPIs your business actually uses." | BI rationalisation and KPI lineage (Domain D8) |
| 3 | "Your platform stays healthy after we leave, and you own the observability." | Package O, deployed in your account |
| 4 | "Your numbers will match, and we'll prove it before cutover." | Equivalence engine and go/no-go evidence packs |
| 5 | "We put our fees behind the outcome." | Fee credit, value floor, flat spend-band pricing |
| 6 | "Senior people who know your industry and your regulator." | Utility and regulated-industry packs; senior-only staffing |

**Buyer-specific value**

| Buyer | What they hear |
|---|---|
| CFO | Quantified savings with a stated method, chargeback by cost centre, and a forecast you can trust |
| CIO / CDO | A platform health index aligned to Snowflake's WAF pillars, a roadmap, and AI-readiness |
| CISO | Least-privilege engagement, access hygiene evidence, masking coverage, agent identity controls |
| Platform owner | Remediation-as-code PRs, alerts with runbooks, and fewer 2 a.m. incidents |
| Business owner | Fewer, trusted reports with one definition per KPI |

### 4.5 When ALTITUDE Is Not the Right Choice

Saying this openly builds trust and protects margin.
- **A 150+ person, multi-country programme with offshore factory economics.** A global SI fits better; ALTITUDE can act as the diagnostic and validation partner alongside it.
- **Lowest-rate staff augmentation.** Not the model.
- **A very small estate** (annual Snowflake spend below the qualification threshold in the rubric). The free D0 Snapshot is enough; a Deep Diagnostic would not pay back.
- **The buyer wants a tool, not a partner.** Buy SaaS.

### 4.6 Moat Analysis

**What is *not* a moat:** SQL conversion (free from Snowflake), generic LLM prompting, dashboards, WAF control checks.

**What can become a moat:**
1. **The Pattern Library and diagnostic check catalogue as data.** Verified mappings, known issues and checks, each with a test, detector, fix, value model and observed frequency. It compounds with every engagement.
2. **Equivalence evidence** that auditors accept. Trust is sticky.
3. **Recurring observability and run services.** Once Package O and the agents run a client's cost, quality and access hygiene, switching costs are real.
4. **Anonymised benchmarks.** With consent, diagnostics data becomes peer benchmarks such as "your idle-credit share is in the worst quartile of utilities". No new entrant has this data.
5. **Vertical depth and partner leverage.** The white-label edition turns smaller competitors into distribution.

**Strategic rules:** *wrap SnowConvert AI and Cortex Code, never fight them.* *Run Snowflake's WAF assessment as one input to Package D, never compete with it.* Both keep ALTITUDE aligned with Snowflake's incentives.

### 4.7 Proof Plan: Turning Claims into Evidence (first 12 months)

| Proof asset | Target date | Why it matters |
|---|---|---|
| D0 Snapshot (scripts first, Native App later) | Month 2 | Lets every first meeting demonstrate differentiators 1 and 6 live |
| Open-source semantic-drift checker | Month 3 | Credibility for differentiator 4; developer reach |
| 3 design-partner case studies with **measured** value (identified vs realised) | Month 9 | The single most important sales asset |
| First "State of Snowflake Estates" anonymised benchmark | Month 12 | Thought leadership; the benchmark moat |
| SOC 2 Type I | Month 12–15 | Clears procurement |
| Snowflake partner tier upgrade and Marketplace listing | Month 9–15 | Account-team visibility |

---

## 5. Business Model, Offer Ladder & Unit Economics

### 5.1 Revenue Lines

| Line | Description | Margin profile | Timing |
|---|---|---|---|
| **Accelerated services** | Package D diagnostics, remediation sprints, assessments, migration sprints, implementations, AI-ready programmes | 35–50% gross (platform leverage) | Day 1 — funds the company |
| **Observability subscriptions (Package O)** | In-account observability data product, flat by spend band | 60–75% gross after setup | From month 3 |
| **Managed run service** | Agentic operations: cost, performance, DQ, access, release-change management, L2/L3 support | 45–60% gross, recurring | From first migration go-live |
| **Platform licence** | Client- or partner-operated ALTITUDE (assessment, factory, run fleet) | 70–85% gross | Year 2 |
| **Partner edition** | White-label for SIs/independents, per-seat + per-project | 75%+ | Year 2–3 |
| **Marketplace apps** | Snowflake Native Apps (e.g. FinOps Sentinel, AI-Readiness Scorer) on Snowflake Marketplace | High, low-touch | Year 1–2 (good lead-gen) |

### 5.2 Flywheel

```
D0 Snapshot (free, in-account)
   → Package D — Deep Diagnostics (evidence + quantified suggestions)
      → Remediation sprints ──▶ Package O — Observability subscription
         → Managed Run (agents) → Migration Factory / AI-Ready (expansion)
            → every engagement grows the Pattern Library, check catalogue and benchmarks
```

### 5.3 Offer Ladder

| Step | Package | Primary buyer | Typical size (hypothesis) | Natural next step | Target conversion (hypothesis) |
|---|---|---|---|---|---|
| 0 | **D0 Snapshot**: free, automated, in-account | Platform owner | Free | Package D | 25–35% |
| 1 | **Package D**: Platform Deep Diagnostics | CDO / CIO / CFO | $20–150K | Remediation sprint and/or Package O | ≥50% within 60 days |
| 2 | **Remediation sprint**: implements Package D suggestions | Platform owner | $40–150K | Package O | ~40% |
| 3 | **Package O**: Platform Observability add-on | Platform owner / FinOps | Setup + $3–25K/month | Managed Run (O3) | ~30% |
| 4 | **Managed Run**: agents + SRE | CIO | Annual subscription | Migration / AI-Ready | — |
| 5 | **Migration Factory / AI-Ready programme** | CIO / CDO | $250K–$several M | Run expansion | — |

### 5.4 Unit-Economics Guardrails (Hypotheses to Validate on the First 10 Deals)

- Blended gross margin of **≥45%** on packages, and **≥60%** on Package O subscriptions after the setup month.
- **Automation leverage.** A Standard Package D (D2) should need no more than ~1.5 senior FTE-months. If it takes more, the check catalogue is not automated enough.
- **Payback on acquisition cost under 6 months** for the motion led by Package D.
- **No fixed-price migration** without a paid assessment first; estimate confidence bands are priced in.
- **Recurring revenue at ≥30% of total by month 24**, made up of Package O, Managed Run and platform licences.

---

# PART II — FLAGSHIP ENTRY PACKAGES

## 6. Package D — Platform Deep Diagnostics

### 6.1 Purpose & Promise

Package D is a metadata-only, evidence-backed diagnostic of an existing Snowflake estate, covering one account or many. It answers five executive questions:

1. **Where are we wasting money?**
2. **Where are we exposed?**
3. **What is likely to break?**
4. **Which reports and KPIs can we trust, and which can we retire?**
5. **What stops us being AI-ready?**

It turns every answer into a prioritised, costed suggestion that is ready to implement as code.

> **The promise:** *Every finding comes with evidence from your account, a dollar or risk value with its method, a confidence score, and the fix with its rollback.*

### 6.2 How It Goes Beyond a Free WAF Scan

Snowflake's Cortex Code WAF assessment skill is a good, free control-level check. Package D **runs it as one input**, aligns its scorecard to the same five WAF pillars, and then goes further.

| Dimension | Free WAF assessment | Package D |
|---|---|---|
| Scope | Control-level checks across the 5 WAF pillars | 10 domains: the 5 WAF pillars plus architecture, BI/consumption, AI-readiness and operating model |
| Depth | Account configuration | Workload, query signature, pipeline, object, report and KPI level |
| Quantification | Ratings and prioritised improvements | Annualised dollar value (p50 and conservative), risk score, effort, confidence |
| Root cause | Individual findings | Root-cause clusters, e.g. "38% of BI compute comes from 11 query signatures behind 4 dashboards" |
| Time | Current state | Trends over up to 365 days, or longer with the Package O archive |
| Access | ACCOUNTADMIN or a role with `ACCOUNT_USAGE` access | Least-privilege `SNOWFLAKE` database roles; no row data |
| Output | HTML report | Executive readout, findings register, backlog, remediation-as-code PRs, savings model, re-baselineable snapshot |
| Human insight | None | Stakeholder interviews, operating-model and contract/capacity assessment |
| After the report | Blueprint guidance | Fee credit into remediation; Package O measures realised value |

### 6.3 Diagnostic Domains

| # | Domain | WAF pillar | Key questions | Primary evidence (verify view names and edition requirements per engagement) |
|---|---|---|---|---|
| D1 | **Cost & FinOps** | Cost Optimization | Where does spend go, what is waste, and is the capacity commitment right-sized? | `METERING_DAILY_HISTORY`, `WAREHOUSE_METERING_HISTORY`, `QUERY_ATTRIBUTION_HISTORY`, serverless histories, `STORAGE_USAGE`, `TABLE_STORAGE_METRICS`, contract price (client input) |
| D2 | **Performance & Workload** | Performance Efficiency | Are warehouses matched to workloads, and which query signatures dominate? | `QUERY_HISTORY` (incl. parameterised hash), `WAREHOUSE_LOAD_HISTORY`, `QUERY_ACCELERATION_ELIGIBLE`, `AUTOMATIC_CLUSTERING_HISTORY` |
| D3 | **Reliability & Pipelines** | Reliability | What fails, how often, and what does it break downstream? | `TASK_HISTORY`, `COPY_HISTORY`, `PIPE_USAGE_HISTORY`, dynamic-table refresh history, dbt artifacts, event tables |
| D4 | **Security & Access** | Security & Governance | Who can do what, and where are the exposures? | `LOGIN_HISTORY`, `USERS`, `GRANTS_TO_ROLES`, `GRANTS_TO_USERS`, network policies, Trust Center findings |
| D5 | **Governance & Data Quality** | Security & Governance | Is sensitive data protected and owned, and is quality measured? | `TAG_REFERENCES`, `POLICY_REFERENCES`, `ACCESS_HISTORY` (Enterprise Edition+), DMF results, comment coverage |
| D6 | **Operational Excellence & DataOps** | Operational Excellence | Is change controlled, and is the platform monitored? | IaC/Git evidence, environment strategy, DDL provenance, alert inventory, interviews |
| D7 | **Data Architecture & Modelling** | Extension | Is the estate layered and lean, or sprawling? | Object inventory, view depth, duplicate-table signatures, unused objects, clones, Time Travel settings, Iceberg usage |
| D8 | **Consumption & BI Layer** | Extension | Which reports and KPIs matter, which are duplicates, and what do they cost? | BI metadata (Power BI, Tableau, Cognos, MicroStrategy APIs/exports), query tags, client application in `QUERY_HISTORY` |
| D9 | **AI Readiness** | Extension (WAF agent guidance applies across pillars) | Can Cortex and agents run here safely and usefully? | EAIRN 8-pillar checks on Snowflake: semantic views, Cortex Search services, agent roles, comment and classification coverage, Cortex usage history |
| D10 | **Operating Model & Commercials** | Operational Excellence | Who owns the platform, is there a FinOps cadence, and is the contract right-sized? | Interviews, chargeback practice, skills inventory, capacity burn-down vs commitment |

### 6.4 Diagnostic Check Catalogue (Sample; Stored as Data)

Thresholds are **rubric references, never literals in code**. Each check has a SQL detector, a value model and a remediation template.

| Check ID | What it detects | Typical suggestion | Value model |
|---|---|---|---|
| DX-COST-01 | Idle-heavy warehouses (credits billed while no queries run) | Shorter auto-suspend; consolidate warehouses | Idle credits × contract price, annualised |
| DX-COST-02 | Oversized warehouses (low queueing, short runtimes, large size) | Downsize, with a performance guardrail | Credit delta at lower size |
| DX-COST-03 | Repeated identical query signatures that bypass the result cache | Cache-friendly design, or materialise via a dynamic table | Repeat executions × average cost |
| DX-COST-04 | Daily full reloads of large tables | Incremental `MERGE`, streams or dynamic tables | Bytes rewritten × cost factor |
| DX-COST-05 | Serverless creep: clustering, search optimisation or MV cost with no pruning or latency benefit | Remove or retune | Serverless credits − measured benefit |
| DX-COST-06 | Storage waste: long Time Travel on staging, stale clones, permanent tables that should be transient | Retention and table-type changes | TB × storage price |
| DX-COST-07 | Untagged spend with no cost-centre attribution | Tag taxonomy and enforcement | Risk/governance value; enables chargeback |
| DX-COST-08 | Capacity commitment over- or under-run forecast | Contract strategy before renewal | Over-commit $ or overage exposure |
| DX-PERF-01 | Queueing on BI warehouses at peak | Multi-cluster scaling policy | SLA risk; user-hours lost |
| DX-PERF-02 | Spilling to local or remote storage | Resize or rewrite | Runtime × credits |
| DX-PERF-03 | Poor pruning on large, frequently filtered tables | Clustering candidate, with a cost-benefit model | Scan reduction vs clustering cost |
| DX-PERF-04 | Top query signatures by cost with anti-patterns (exploding joins, `SELECT *`, non-sargable filters) | Rewrite pack with before/after test | Signature cost × expected reduction |
| DX-REL-01 | Failing or retried tasks and their downstream blast radius | Fix root cause; add alerting | Incident cost; SLA risk |
| DX-REL-02 | Freshness SLA misses on Tier-1 tables | Scheduling and dependency redesign | SLA risk |
| DX-REL-03 | Pipelines that run under personal user credentials | Service identities | Key-person and security risk |
| DX-REL-04 | Tier-1 data with no replication or failover where the RPO requires it | DR design | Risk score |
| DX-SEC-01 | Humans without MFA; service users authenticating by password | Enforce MFA; key-pair or OAuth | Risk score |
| DX-SEC-02 | Number of ACCOUNTADMIN grants and frequency of use | Break-glass model | Risk score |
| DX-SEC-03 | Direct grants to users, orphan roles, dormant users and grants | Role model clean-up | Risk score |
| DX-SEC-04 | Accounts or users without a network policy | Network rules | Risk score |
| DX-SEC-05 | Sensitive or classified columns without masking | Tag-based masking | Risk score; regulatory exposure |
| DX-GOV-01 | Tier-1 objects with no owner tag or comment | Ownership bootstrap from usage | Governance value |
| DX-GOV-02 | Tier-1 tables with no DMFs or tests | DQ rule pack | Incident avoidance |
| DX-GOV-03 | Objects unused for longer than the rubric window | Archive, then drop | Storage $; reduced attack surface |
| DX-OPS-01 | Production DDL executed outside IaC/CI | DataOps pipeline | Change-failure risk |
| DX-OPS-02 | No alerts for credit spikes or failed Tier-1 tasks | Alert pack (Package O) | Detection lead time |
| DX-ARCH-01 | View-on-view depth beyond the rubric; duplicate tables (same schema and size signature) | Consolidate or materialise | Compute and storage $ |
| DX-BI-01 | Duplicate or near-duplicate reports (similarity of structure and query, plus usage) | Retain / merge / retire recommendations | Licence, refresh-compute and support $ |
| DX-BI-02 | The same KPI name computed with different logic | Single certified definition in a semantic view | Decision risk |
| DX-BI-03 | Dashboards whose refresh cost exceeds their use (cost per view) | Change refresh cadence or retire | Compute $ |
| DX-AI-01 | No semantic views for the top KPI domains | Semantic view build | AI-readiness score |
| DX-AI-02 | Cortex or agent usage without budgets or dedicated roles | Agent identity and budget controls | Cost and risk |
| DX-AI-03 | Tier-1 column comment coverage below the rubric threshold | Documentation agent with steward approval | AI-readiness score |

The full catalogue targets 120+ checks by month 9, each versioned with a `last_verified` date.

### 6.5 How Suggestions Are Produced: the Suggestion Engine

```
Harvest (read-only, in-account)
  → Signals (SQL detectors per check, run against the snapshot)
    → Rule evaluation (rubric thresholds by reference)
      → Root-cause clustering (query signature · warehouse · dashboard · pipeline · owner)
        → Value model ($ from contract price × modelled credits; risk = likelihood × impact)
          → Remediation generator (SQL / Terraform / dbt drafts, each with rollback)
            → AI narrative (Cortex in-account): explanation, confidence, rationale
              → Human review (mandatory below 0.80 confidence; sampled above)
                → Prioritisation (value × effort × risk) → Publish to snapshot
```

**Suggestion record (canonical, stored as data)**

```yaml
suggestion:
  id: SUG-0142
  snapshot_id: SNAP-ACME-2026-10-01
  check_id: DX-COST-01
  domain: D1
  waf_pillar: cost_optimization
  title: "Shorten auto-suspend on four BI warehouses"
  evidence_refs: [EV-WH-0031, EV-WH-0032, EV-WH-0040, EV-WH-0041]
  affected_objects: [WH_BI_PROD, WH_BI_ADHOC, WH_BI_FIN, WH_BI_OPS]
  value:
    annualised_usd: { p50: 84000, conservative: 61000 }      # illustrative
    method: "idle credits (last 90d) × contract price, annualised; conservative = p20 of daily idle"
  risk_reduction: null
  effort: { size: S, hours_p50: 6 }
  confidence: 0.91
  rationale: "Idle share above rubric threshold on 4 of 6 BI warehouses; no cache-dependent workloads detected"
  remediation:
    type: sql
    artifact_ref: generated/remediation/SUG-0142.sql          # AUTO-GENERATED — DO NOT EDIT
    autonomy: L2
    rollback_ref: generated/remediation/SUG-0142.rollback.sql
  kpis_to_watch: [KPI-COST-007, KPI-PERF-002]                  # Package O measures realised value
  priority: { quadrant: quick_win, rank: 3 }
  status: proposed       # proposed → accepted → implemented → value_realised | rejected
  reviewer: null
```

**Prioritisation quadrants**

| Quadrant | Rule (by rubric) | Horizon |
|---|---|---|
| **Quick wins** | High value, low effort | First 30 days |
| **Strategic** | High value, high effort | 90-day plan / roadmap |
| **Hygiene** | Low value, low effort | Batched into a sprint |
| **Defer** | Low value, high effort | Backlog with rationale |

### 6.6 Engagement Method (D2 Deep, 4 Weeks)

| Week | Activities | Client involvement | Interim output |
|---|---|---|---|
| 0 | Kickoff; run the access bootstrap script; permission manifest; credit cap for the diagnostics warehouse; stakeholder map; contract price input | Platform owner 2h; security approval | Access confirmed |
| 1 | Automated harvest and signal computation; BI metadata harvest; free WAF assessment run as an input; 6–10 stakeholder interviews | Interviewees, 45 min each | Data completeness report |
| 2 | Root-cause clustering; value modelling; draft scorecard | — | **Quick-win memo** (value delivered in week 2) |
| 3 | Remediation drafts; validation workshop with the platform team to remove false positives; roadmap | Platform team, 2 × 2h | Validated findings register |
| 4 | Executive readout; handover of all artifacts; baseline snapshot sealed | Executives, 90 min | Final deliverables |

### 6.7 Tiers & Indicative Pricing (US Market; Hypotheses to Validate)

| Tier | Scope | Duration | Team | Indicative fee |
|---|---|---|---|---|
| **D0 Snapshot** | 1 account; automated D1–D5 checks; top-10 findings; 1-hour readout | 1 week | ~0.2 FTE | Free (lead generation) |
| **D1 Essentials** | 1 account; D1–D7; quick wins and 90-day plan | 2 weeks | 1 senior | $20–30K |
| **D2 Deep** *(flagship)* | Up to 3 accounts; all 10 domains incl. one BI tool; interviews; remediation-as-code | 4 weeks | Lead + engineer | $45–75K |
| **D3 Enterprise** | Organisation-wide, multi-account; several BI tools; operating model; contract/capacity strategy; board pack | 6 weeks | 3 | $90–150K |

Snowflake partner funding programmes may co-fund diagnostics for qualifying accounts; verify current programmes with the partner team.

### 6.8 Commercial Guarantees (Selected per Deal)

| Guarantee | Terms | Guardrail |
|---|---|---|
| **Fee credit** | 100% of the D1 or D2 fee credited against a remediation sprint or Package O signed within 60 days | Applies once per account |
| **Value floor** | If the identified annualised opportunity (p50) is below 3× the fee, ALTITUDE credits the difference | D2/D3 only; annual Snowflake spend must be above the qualification threshold; "identified opportunity" defined in the contract; credit capped at the fee |
| **Re-baseline** | A free D0 re-run at 90 days to show realised improvement | Requires client implementation of accepted suggestions |

### 6.9 Deliverables (All Generated from One Sealed Snapshot)

1. **Executive readout** (12–15 slides): Platform Health Index, scorecard by domain and WAF pillar, top 10 suggestions, savings and risk model, roadmap.
2. **Diagnostic report:** findings by domain, method, assumptions, evidence appendix.
3. **Findings register** (sheet/CSV): every suggestion with evidence, value, method, effort and confidence.
4. **Remediation backlog:** importable into Jira or Azure DevOps.
5. **Remediation-as-code pack:** SQL, Terraform and dbt drafts as a pull request, header-stamped, each with a rollback.
6. **Savings & risk model:** with every assumption explicit and contract price as an input.
7. **Baseline snapshot:** immutable; the basis for re-diagnosis and for Package O.

### 6.10 Access & Security Requirements

- A dedicated read-only role granted the relevant **`SNOWFLAKE` database roles** (e.g. `USAGE_VIEWER`, `GOVERNANCE_VIEWER`, `OBJECT_VIEWER`, `SECURITY_VIEWER`), checked against current documentation. `ORGANIZATION_USAGE` views need organisation-level access for multi-account scope. **No ACCOUNTADMIN.**
- A dedicated X-Small diagnostics warehouse with a resource monitor capped at a credit budget agreed upfront.
- Key-pair authentication. Access is revoked at close and the access log is handed to the client.
- **Metadata only.** Analysis runs inside the client account, as scripts or a Native App. Only aggregates and findings leave it, and in Native mode nothing leaves.

### 6.11 Scorecard & Maturity Model

- Each domain is scored **1–5** (Initial · Developing · Defined · Managed · Optimised) from weighted check outcomes held in the rubric.
- The **Platform Health Index (0–100)** rolls the domains up and is also shown by WAF pillar.
- Scores are reproducible: the same snapshot and rubric version always produce the same numbers.
- Optional **peer benchmark** (anonymised, with consent, once the sample size allows): quartile position by industry and spend band.

### 6.12 Package Success KPIs

| KPI | Target |
|---|---|
| Identified annualised value vs fee | ≥ 3× |
| Top-10 suggestions accepted by the client platform team | ≥ 70% |
| False-positive rate after the week-3 validation workshop | < 10% |
| Conversion to remediation or Package O within 60 days | ≥ 50% |
| Realised value at the 90-day re-baseline | ≥ 40% of the identified quick-win value |

### 6.13 From Findings to Next Steps

| Dominant finding pattern | Recommended next package |
|---|---|
| High untagged spend, no monitors, idle-heavy warehouses | FinOps remediation sprint + Package O |
| Critical security findings | Security hardening sprint |
| Heavy BI duplication, conflicting KPIs | BI rationalisation programme |
| Brittle legacy ETL or sources still on appliances | Migration assessment (Part III) |
| Low AI-readiness score | AI-Ready programme (Section 19) |
| Recurring pipeline failures, no on-call | Managed Run (Package O3) |

---

## 7. Package O — Platform Observability (Add-on)

### 7.1 Purpose & Positioning

Package O is continuous, client-owned observability of the Snowflake platform, covering cost, performance, reliability, security, governance, data quality and AI usage. It is delivered as a **data product inside the client's account**, not as a third-party SaaS.

It is sold as an add-on in three places:
- **To Package D.** The one-time diagnostic becomes a living scorecard.
- **To migrations.** It provides observability for hypercare.
- **As the foundation of the Managed Run Service.** The agent fleet reads from it.

**Why it matters commercially:**
- It turns project revenue into recurring revenue.
- It keeps ALTITUDE in the account every month.
- It produces the before-and-after evidence that proves ALTITUDE's value.

### 7.2 Package O vs the Alternatives

| Alternative | Limitation | Package O |
|---|---|---|
| Snowsight dashboards and native cost management | Mostly single-account views; native usage history is retained for about a year; no chargeback model or cross-domain correlation | Multi-account; long-term archive; chargeback; correlation across cost, performance and security |
| Snowflake Trail (event tables, logs, traces, alerts) | Rich telemetry for code and pipelines, but the KPIs, dashboards and operating model are left for you to build | Built on Trail and `ACCOUNT_USAGE`, with KPIs, a semantic layer, alerts and runbooks provided |
| FinOps/observability SaaS | Often copies telemetry out of the account; often priced against spend; narrower scope | In-account and client-owned, with an open semantic model; integrates with those tools if the client already has them |
| DIY by the platform team | Slow to build and rarely maintained | Maintained as a product; the KPI catalogue is updated with Snowflake behaviour changes |

### 7.3 Architecture

```
Client Snowflake accounts (DEV / QA / UAT / PROD / …)
  ACCOUNT_USAGE · ORGANIZATION_USAGE · INFORMATION_SCHEMA · Event tables (Trail) · BI metadata
        │  config-driven harvest — sources, schedules and load strategies stored as data
        ▼
OBS database (central account) — one codebase, N deployments
  RAW       immutable, append-only archive; retention beyond the native window
  CURATED   conformed facts and dimensions: warehouse, query signature, user, role,
            object, tag, task, pipeline, dashboard, cost centre
  KPI       dynamic tables implementing the KPI catalogue
  SEMANTIC  semantic views holding certified KPI definitions
        │
        ├── Dashboards        Snowsight / Streamlit / Power BI / Tableau
        ├── Alerts            Snowflake Alerts → Slack / Teams / PagerDuty / ServiceNow
        ├── Ask-the-platform  Cortex Agent in Snowflake Intelligence over the semantic views
        └── Agent tools       Cost Sentinel, Rightsizer, Access Hygiene … (O3 / Managed Run)
```

- **Cross-account consolidation** uses secure data sharing or replication to the central account.
- **RAW immutability** is enforced by a CI kill-test: no `UPDATE` or `DELETE` grants are allowed on RAW.
- **Provenance.** The design reflects patterns the founder has proven before. It is rebuilt clean-room for ALTITUDE (Section 37).

### 7.4 KPI Catalogue (~80 KPIs, Phased, Stored as Data)

| Domain | Core tier (MVP, ~23 KPIs) | Extended tier (~45) | Advanced tier (~12) |
|---|---|---|---|
| **Cost** | Credits and $ by account, warehouse and day; cost by tag/cost centre; month-on-month trend; forecast vs budget | Idle-credit share; cost per query signature; serverless breakdown; storage by type | Unit economics (cost per data product, per dashboard view, per agent answer); commitment burn-down forecast |
| **Performance** | p50/p95 query time by warehouse; queued time | Spill bytes; pruning efficiency; cache-hit rate | Regression detection per query signature |
| **Reliability** | Task success rate; failed tasks (24h) | Freshness SLA attainment; dynamic-table refresh lag; pipe latency | MTTR; downstream blast radius |
| **Security** | MFA coverage; ACCOUNTADMIN count; failed logins | Dormant users and grants; direct grants; network-policy coverage | Anomalous access patterns |
| **Governance & DQ** | Tag coverage; owner coverage on Tier-1 objects | Masking coverage on classified columns; DMF pass rate | Data product health score |
| **Usage & adoption** | Active users; queries by client tool | Top consumers; unused objects | Adoption by domain |
| **AI / Cortex** | Cortex credits by function and agent | Cost per accepted answer; latency | Evaluation drift |
| **Platform Health Index** | — | Monthly recomputation of the Package D scorecard by WAF pillar | Peer benchmark position |

**KPI definition (example)**

```yaml
kpi:
  id: KPI-COST-007
  name: "Idle credit share"
  domain: cost
  tier: extended
  definition: "compute credits billed while the warehouse had no running queries / total compute credits"
  grain: [account, warehouse, day]
  sources: [WAREHOUSE_METERING_HISTORY, WAREHOUSE_LOAD_HISTORY]
  freshness_sla_ref: rubric.obs.freshness.cost
  alert:
    threshold_ref: rubric.obs.idle_share_alert
    route_ref: tenant.alert_routes.finops
    runbook: RB-COST-IDLE
  owner_role: PLATFORM_OWNER
  waf_pillar: cost_optimization
  linked_checks: [DX-COST-01, DX-COST-02]
```

### 7.5 Dashboards

| # | Dashboard | Audience |
|---|---|---|
| 1 | Executive Cost & Value | CFO, CDO |
| 2 | Platform Health (Health Index by WAF pillar) | CIO, platform owner |
| 3 | Workload & Performance | Engineering |
| 4 | Pipelines & Freshness | DataOps |
| 5 | Security & Access | CISO |
| 6 | Governance & Quality | CDO, stewards |
| 7 | AI & Cortex Usage | AI lead, FinOps |
| 8 | Chargeback statements (monthly, per cost centre, exportable) | Finance, budget owners |

### 7.6 Alerts & Runbooks

**Alert classes:**
- Credit anomaly against the forecast band
- Budget threshold breach
- Failed Tier-1 task
- Freshness SLA breach
- ACCOUNTADMIN use
- New user without MFA
- Masking gap on a newly classified column
- Cortex spend spike
- Query-signature performance regression

Each alert's severity, route, runbook, suppression window and owner are stored as data. Routing is tested monthly.

### 7.7 Tiers & Indicative Pricing (US Market; Hypotheses to Validate)

| Tier | Includes | Onboarding | Setup fee | Subscription |
|---|---|---|---|---|
| **O1 Observe** | Core KPIs; dashboards 1, 2 and 4; core alerts; up to 2 accounts; quarterly health review | 3–4 weeks | $15–25K | $3–5K / month |
| **O2 Observe+** | Full catalogue; all 8 dashboards; chargeback; anomaly detection; ask-the-platform agent; monthly FinOps review; up to 5 accounts | 5–6 weeks | $30–45K | $6–10K / month |
| **O3 Observe & Operate** | O2 + agent fleet at L1–L2; business-hours alert response; quarterly optimisation sprint; annual Package D re-run | 6–8 weeks | $40–60K | $12–25K / month, by spend band |

**Pricing principle:** charge **flat, by spend band**, never as a percentage of Snowflake spend, so ALTITUDE gains nothing when the client's spend rises. A self-serve O1 Native App on Snowflake Marketplace is a later option.

### 7.8 Service Levels for the Add-on

| Measure | Target (stored in rubric) |
|---|---|
| KPI-layer freshness | Per-KPI SLA (e.g. hourly for cost, daily for governance) |
| Harvest success | ≥ 99% of scheduled runs per month |
| Alert routing test | Monthly |
| KPI catalogue update after a relevant Snowflake behaviour change | Within 30 days |
| Monthly / quarterly review delivered | 100% |

### 7.9 Ownership, Exit & Security

- **The client owns the data and the deployed dashboards.** Everything runs under the client's roles, and ALTITUDE's access is least-privilege.
- **Exit.** If the client leaves, the deployment keeps running. ALTITUDE stops updating the catalogue and agents.
- **ADR required: code licensing model.** Either (a) a perpetual internal-use licence to the deployed code, or (b) the core engine as a licensed Native App with client-owned configuration and data. (b) protects the IP; (a) removes procurement objections.
- **Nothing leaves the account** unless the client opts in to anonymised benchmarking.

### 7.10 Onboarding Plan (O2, 6 Weeks)

| Week | Activities |
|---|---|
| 1 | Access, configuration and source registry; first harvest |
| 2 | RAW archive and CURATED model live; backfill from available history |
| 3 | Core KPIs; Executive Cost & Value and Platform Health dashboards |
| 4 | Extended KPIs; chargeback model agreed with finance |
| 5 | Alerts and runbooks; ask-the-platform agent with golden questions |
| 6 | Handover, training, first monthly review |

### 7.11 Package Success KPIs

| KPI | Target |
|---|---|
| Time to first dashboard | ≤ 3 weeks |
| Spend attributed to a cost centre by month 3 | ≥ 95% |
| Cost anomalies detected before the invoice | ≥ 90% |
| Subscription net revenue retention | ≥ 110% (expansion to O3 / Managed Run) |

### 7.12 How D and O Work Together: the Suggestion-to-Value Loop

```
Package D snapshot (baseline Health Index, suggestions with kpis_to_watch)
   → client implements suggestions (status: implemented)
      → Package O measures the linked KPIs before and after
         → realised value recorded on the suggestion (status: value_realised)
            → quarterly business review: identified vs realised value, Health Index delta
               → new findings feed the next sprint
```

**This loop is ALTITUDE's signature.** Most partners report what they *found*. ALTITUDE reports what was *realised*, measured in the client's own account.

---

# PART III — MIGRATION ENGINE

## 8. Migration Patterns

The platform scores every candidate pattern against the harvested estate (Section 32) and recommends one per **workload wave**, not per programme — real programmes mix patterns.

### 8.1 Pattern Summary

| Pattern | Definition | Best when | Avoid when | Typical speed / risk |
|---|---|---|---|---|
| **Lift-and-shift (rehost-like)** | Move schemas, data and code with minimal logic change; preserve interfaces | Hard deadline (licence/hardware), stable workloads, low tech debt, need to exit fast | Heavy procedural row-by-row logic; appliance-specific design; intent to modernise anyway | Fastest; carries legacy debt and cost risk |
| **Re-platform (lift-tweak-shift)** | Convert to Snowflake idioms where cheap (set-based SQL, Snowflake Scripting, tasks, Snowpipe) while keeping the data model | Default for most EDWs; balances speed and value | Model is fundamentally broken | Moderate; best value/risk ratio |
| **Re-architect (refactor)** | Redesign model and pipelines: medallion/Data Vault/dimensional, dbt, dynamic tables, streaming, data products | Hadoop exits, spaghetti ETL, strong appetite for modernisation | Fixed short deadlines | Slowest; highest long-term value |
| **Greenfield** | New platform, no legacy to migrate (or legacy left in place) | New business units, digital products, M&A carve-outs, AI-first initiatives | — | Fastest to value if scoped to products |
| **Hybrid / coexistence** | Snowflake runs alongside legacy for a period; federated or replicated access | Large estates, long tails, regulatory freeze periods | Indefinite coexistence with no decommission date | Reduces cutover risk; doubles run cost |
| **Open-lakehouse (Iceberg)** | Land data as Apache Iceberg (Snowflake-managed or external catalog) | Multi-engine strategy, data-lake exits, avoiding lock-in concerns | Teams needing simplest operations | Moderate; requires catalog strategy |
| **Virtualise-then-migrate** | Query-translation/virtualisation layer lets apps run unchanged while data moves | Thousands of embedded app queries you can't touch quickly | As a permanent state | Fast app cutover; adds a dependency |

### 8.2 Pattern Playbooks

#### 8.2.1 Lift-and-Shift
**Steps:** inventory → dead-code pruning (still mandatory) → schema conversion → bulk historical load → code conversion (SnowConvert AI) → EWI remediation → functional validation → schedule re-pointing → parallel run → cutover.
**Accelerators:** auto-pruning from query history; bulk DDL generator; batch EWI-fix agent; L1/L2 reconciliation generator; scheduler translator (Control-M/Autosys/SQL Agent → Tasks or orchestrator).
**Best practices:**
- Still remove unused objects — lift-and-shift does not mean lift-and-shift *everything*.
- Pre-agree a **"modernise later" backlog** with named owners; otherwise the debt is permanent.
- Apply Snowflake guardrails from day one regardless: auto-suspend, resource monitors, functional roles.
**Known issues:** appliance-era full-refresh patterns get expensive; procedural loops kill performance; physical design hints (PI, indexes, distribution keys) become meaningless — and some teams try to emulate them.

#### 8.2.2 Re-platform
**Steps:** as lift-and-shift, plus targeted refactors scored by *(cost saved + performance gain) / effort*: cursor loops → set-based SQL, full reloads → incremental `MERGE`/streams, staging tables → dynamic tables, batch files → Snowpipe.
**Accelerators:** anti-pattern detector (Section 31) that ranks refactor candidates with estimated credit savings.
**Best practice:** cap refactor scope per wave (e.g. top 20% of objects by run cost) so the deadline survives.

#### 8.2.3 Re-architect
**Steps:** business capability map → target data model (medallion + dimensional or Data Vault 2.0 raw vault) → data contracts → dbt/dynamic tables → semantic layer → BI rebuild → data products.
**Accelerators:** legacy-model-to-target mapper (AI-proposed, steward-approved), dbt project scaffolder with stg/int/dim/fct/agg conventions, contract generator, semantic view generator.
**Known issues:** scope creep; business re-validation of every KPI; long dual-running. Mitigate with **domain-by-domain strangler** delivery.

#### 8.2.4 Greenfield
See Section 15 — a 6–10 week "Snowflake Foundation" landing zone followed by product-aligned delivery.

#### 8.2.5 Hybrid / Coexistence
**Mechanisms:** CDC replication legacy → Snowflake; reverse feeds for not-yet-migrated consumers; Iceberg as shared format; federated views via data virtualisation (e.g. Denodo) during transition.
**Rule:** every coexistence arrangement has a **decommission date and exit criteria** stored in the plan; the platform alerts when coexistence cost exceeds threshold.

#### 8.2.6 Open-Lakehouse (Iceberg)
**Decisions to make (recorded as ADRs):** Snowflake-managed vs externally-managed Iceberg; catalog (Snowflake Open Catalog/Polaris, Glue, Unity, other REST catalogs); which engines write vs read; compaction ownership; governance enforcement points.
**Known issues:** feature parity differences between native and Iceberg tables; multi-writer governance; small-file and compaction management; catalog-sync latency. Verify current Snowflake Iceberg feature matrix per engagement — it changes frequently.

### 8.3 Pattern Recommender (stored as rubric data)

```yaml
pattern_recommender:
  version: 1.0.0
  inputs: [deadline_weeks, procedural_code_share, dead_object_share, model_quality_score,
           appetite_for_change, etl_tool_complexity, regulatory_freeze_windows, budget_band]
  rules:
    - when: "deadline_weeks < 26 and procedural_code_share > 0.4"
      recommend: lift_and_shift
      rationale: "Deadline cannot absorb procedural refactor; schedule refactor backlog post-cutover"
    - when: "model_quality_score < 40 and appetite_for_change >= 3"
      recommend: re_architect
    - default: re_platform
  output_requires: [confidence, rationale, dissent_from_review_board]
```

---

## 9. Migration Lifecycle & Factory Method

### 9.1 Eight Phases with Gates

| Phase | Objective | Key outputs | Exit gate (evidence-based) |
|---|---|---|---|
| **0. Discover** | Understand business drivers, constraints, stakeholders | Drivers, success metrics, constraints register | Sponsor sign-off on objectives and success KPIs |
| **1. Assess** | Harvest and analyse the estate (metadata-only) | Inventory, usage heatmap, dead-code list, complexity scores, dependency graph, risk register, TCO/business case | ≥95% of objects classified; business case approved |
| **2. Plan** | Waves, patterns, target architecture, team, timeline | Wave plan, target architecture ADRs, estimate with confidence band, RAID log | Wave 1 scope frozen; architecture board approval |
| **3. Foundation** | Build Snowflake landing zone | Account/org structure, RBAC, networking, IaC, CI/CD, monitoring, FinOps guardrails | Well-Architected baseline checks pass (Section 14) |
| **4. Convert** | Schema, code, ETL, schedules, BI | Converted artifacts, EWI log, AI-fix log with approvals | Zero open P1 EWIs; peer + AI review complete |
| **5. Move & Validate** | Historical load, CDC, reconciliation, performance tests | Load evidence, reconciliation reports L1–L3, performance benchmarks | Reconciliation thresholds met per table tier |
| **6. Cutover** | Parallel run, go/no-go, switch | Parallel-run comparison, go/no-go pack, rollback plan | Business sign-off; rollback rehearsed |
| **7. Operate & Decommission** | Hypercare, run handover, legacy shutdown | Run book, agent fleet live, decommission evidence, savings realised | Legacy read-only then off; savings booked |

### 9.2 The Factory

Waves run as a factory with **swim lanes**: Schema · Code · ETL · Data · Validation · BI · Security · Ops. Each object is a work item with a state machine:

`Discovered → Classified (keep/retire/rewrite) → Converted → AI-remediated → Reviewed → Unit-tested → Loaded → Reconciled → Performance-tested → UAT-passed → Cut over → Legacy retired`

Every transition records actor (human or agent identity), timestamp, evidence reference, and confidence. Burn-down, throughput, defect-escape rate and rework rate are live on the Progress board.

### 9.3 Wave Design Rules (stored as data)
- Wave 1 = **thin vertical slice** (one subject area, source → BI) proving the whole pipeline, not the easiest tables.
- Group by **dependency clusters** from the lineage graph, not by schema name.
- Regulatory reports and month-end processes never cut over in the last 10 business days of a quarter.
- Each wave ≤ 12 weeks; each wave ends with something a business user uses.

### 9.4 RACI (Abridged)

| Activity | Client exec | Client data owners | Client platform | ALTITUDE delivery | ALTITUDE agents | Snowflake |
|---|---|---|---|---|---|---|
| Objectives & business case | A | C | C | R | S (drafting) | C |
| Estate harvest | I | I | C (grants) | A | R | — |
| Conversion & remediation | I | C | C | A | R (with human approval) | C (tooling) |
| Reconciliation sign-off | I | A | C | R | S | — |
| Go/no-go | A | R | R | R | S (evidence pack) | C |
| Run & optimisation | I | C | A | R | R (L0–L2) | C |

---

## 10. Source Modules

Each module follows the same structure: **Harvest** (what we read, with what privilege) · **Inventory signals** · **Conversion map** (highlights; full map in the Pattern Library) · **Known issues** (severity-ranked) · **Best practices** · **Data movement** · **AI accelerators**.

Severity: **S1** = silent wrong answers, **S2** = failure/rewrite required, **S3** = performance/cost, **S4** = cosmetic/operational.

> All mappings below are starting knowledge. Each must be re-verified against the current Snowflake and SnowConvert AI documentation at engagement start; Snowflake ships behaviour-change bundles regularly. The Pattern Library stores a `last_verified` date per entry.

### 10.1 Teradata

**Harvest:** read-only user with `SELECT` on `DBC` views (`DBC.TablesV`, `ColumnsV`, `IndicesV`, `QryLogV`/DBQL, `AccessRightsV`, `AllRoleRightsV`); BTEQ/TPT/FastLoad/MultiLoad scripts and scheduler definitions from repositories.

**Inventory signals:** DBQL-based usage (12+ months if retained), table skew, `SET` vs `MULTISET`, macros, stored procedures (SPL), volatile/global temporary tables, views-on-views depth, BTEQ script count, utility jobs, QueryGrid links, TASM workload definitions.

**Conversion highlights**

| Teradata | Snowflake | Note |
|---|---|---|
| `MULTISET` table | Table | Direct |
| `SET` table | Table **+ explicit dedupe** | Snowflake has no `SET` semantics |
| Primary Index / PPI / NUPI | None; clustering key only if justified | Do not emulate distribution |
| Volatile table | Temporary table | Session scope semantics differ slightly |
| Macro | Stored procedure / view | |
| SPL stored procedure | Snowflake Scripting (SQL) | Cursor logic → set-based where possible |
| BTEQ script | Snowflake SQL + orchestrator / Snowflake CLI | Control flow (`.IF ERRORCODE`, `.GOTO`) must be rebuilt |
| FastLoad/MultiLoad/TPT | `COPY INTO` / Snowpipe / Openflow | |
| `QUALIFY` | `QUALIFY` | Supported natively |
| `SAMPLE` | `SAMPLE`/`TABLESAMPLE` | Semantics differ |
| `PERIOD` types | Two date/timestamp columns | |
| `COLLECT STATISTICS` | Remove | Not applicable |
| `NOT CASESPECIFIC` columns | Collation spec or `UPPER()` normalisation | See issues |

**Known issues**

| # | Issue | Sev | Detection | Fix pattern |
|---|---|---|---|---|
| TD-01 | `SET` tables silently discarded duplicate rows on insert; Snowflake keeps them | S1 | Inventory flag on every SET table + downstream inserts | Add `QUALIFY ROW_NUMBER()`/`MERGE`-based dedupe in load; reconciliation on distinct counts |
| TD-02 | Case-insensitive comparisons (`NOT CASESPECIFIC`, session mode) become case-sensitive | S1 | Column attributes + predicates on char columns | Collation `en-ci` on columns or normalise at ingestion; test joins/filters |
| TD-03 | Trailing-space handling in `CHAR` comparisons differs | S1 | CHAR columns used in joins | `RTRIM` at load; convert CHAR → VARCHAR |
| TD-04 | Integer date arithmetic / date format literals (`'YYYY-MM-DD'` vs integer dates) | S1 | Parser detects date arithmetic on integers | Explicit `DATEADD`/casts |
| TD-05 | Division of integers returns integer in Teradata; Snowflake returns decimal | S1 | Integer `/` integer | Explicit cast / `FLOOR` / `TRUNC` per intent |
| TD-06 | BTEQ error handling and `.ACTIVITYCOUNT` logic | S2 | Script parser | Snowflake Scripting exceptions + `SQLROWCOUNT` |
| TD-07 | Recursive views and deep view stacks perform differently | S3 | View depth > 5 | Materialise via dynamic tables |
| TD-08 | Teradata-style `UPDATE … FROM` with joins and ambiguous multi-match updates | S1 | Update-join with non-unique source | Pre-aggregate / dedupe source; Snowflake errors or is nondeterministic on multi-match depending on settings |
| TD-09 | TASM workload priorities have no 1:1 equivalent | S3 | TASM definitions | Map workloads → dedicated warehouses + resource monitors |
| TD-10 | Identity columns & `GENERATED ALWAYS` gaps | S4 | DDL | Sequences/`AUTOINCREMENT`; never assume gap-free |
| TD-11 | Timestamp precision & time-zone session defaults | S1 | Session settings harvest | Standardise `TIMESTAMP_NTZ` vs `_TZ` policy upfront |

**Best practices:** harvest DBQL for at least a full fiscal year to catch quarter/year-end jobs; prune ruthlessly (Teradata estates commonly carry large shares of unused objects); convert BTEQ to SQL + an orchestrator rather than re-implementing a BTEQ emulator; treat `SET` tables and case-insensitivity as **programme-level decisions**, not per-object fixes.

**Data movement:** TPT export / parallel unload → cloud object storage (Parquet, compressed) → `COPY INTO`; SnowConvert AI's growing data-migration capability where it fits; CDC for coexistence via third-party tools.

**AI accelerators:** BTEQ-to-Snowflake-Scripting agent (control-flow aware), SET-table dedupe test generator, case-sensitivity risk scanner over all predicates.

### 10.2 Oracle (incl. Exadata)

**Harvest:** account with `SELECT_CATALOG_ROLE`; `DBA_TABLES`, `DBA_TAB_COLUMNS`, `DBA_SOURCE`, `DBA_DEPENDENCIES`, `DBA_OBJECTS`, `DBA_SCHEDULER_JOBS`, AWR/ASH (if licensed — check Diagnostics Pack licensing before use), `DBA_AUDIT_TRAIL`/Unified Audit for usage.

**Conversion highlights**

| Oracle | Snowflake | Note |
|---|---|---|
| `NUMBER` (no precision/scale) | `NUMBER(38, s)` with explicit scale, or `FLOAT` | Snowflake defaults scale 0 |
| `VARCHAR2(n BYTE/CHAR)` | `VARCHAR(n)` (characters) | |
| `DATE` | `TIMESTAMP_NTZ` | Oracle DATE contains time |
| `TIMESTAMP WITH LOCAL TIME ZONE` | `TIMESTAMP_LTZ` | |
| PL/SQL package | Schema + procedures/UDFs; package state → table/session variables | No packages |
| `CONNECT BY` | `CONNECT BY` or recursive CTE | Supported; test ordering |
| Sequences | Sequences | Gaps, no `CURRVAL` parity in all contexts |
| Triggers | Streams + tasks, or move logic into pipelines | Not supported |
| `ROWNUM` | `ROW_NUMBER()` / `LIMIT` | |
| Materialized views | Dynamic tables (usually) | Snowflake MV restrictions |
| Global temporary tables | Temporary/transient tables | |
| `DBMS_*` utilities | Rewritten | Case-by-case |
| DB links | Data sharing / external access / pipelines | |

**Known issues**

| # | Issue | Sev | Fix pattern |
|---|---|---|---|
| OR-01 | Empty string `''` treated as `NULL` in Oracle; distinct in Snowflake | S1 | Normalise `NULLIF(col,'')` at ingestion; review `IS NULL` predicates and concatenations |
| OR-02 | Unscaled `NUMBER` mapped to scale 0 truncates decimals | S1 | Profile max scale (metadata stats or permission-gated sample) → explicit scale |
| OR-03 | `DATE` time component lost when mapped to `DATE` | S1 | Map to `TIMESTAMP_NTZ`; fix downstream comparisons |
| OR-04 | Packages with global state, overloading, autonomous transactions | S2 | Decompose; state tables; redesign autonomous logging |
| OR-05 | Row-by-row `BULK COLLECT`/cursor loops | S3 | Set-based rewrite; AI refactor agent |
| OR-06 | Legacy `(+)` outer joins | S2 | Convert to ANSI joins |
| OR-07 | Triggers for audit/derivation | S2 | Streams/tasks or pipeline logic; audit via `ACCESS_HISTORY` |
| OR-08 | `NLS_*` session settings (date formats, sort, comparison) | S1 | Harvest NLS settings; set explicit formats |
| OR-09 | LOB sizes, `LONG`, `XMLTYPE`, spatial types | S2 | Check current Snowflake size limits; `VARIANT`/`GEOGRAPHY`; externalise large binaries |
| OR-10 | Exadata performance relied on smart scan/HCC/partition pruning | S3 | Clustering keys only for very large, frequently filtered tables; measure first |
| OR-11 | Oracle licensing exposure during migration (extra cores for unload, diagnostic packs) | S4 | Licence review in Phase 0 |

**Data movement:** parallel unload (Data Pump → staged files, or extraction tools) → object storage → `COPY`; CDC via GoldenGate, Qlik Replicate, Fivetran HVR, Striim, Debezium or Openflow connectors (verify current connector availability).

**Best practices:** decide numeric and empty-string policy before the first table moves; inventory `DBMS_SCHEDULER` jobs and external DB links early (they are the hidden integrations); put PL/SQL refactoring under the AI refactor agent with mandatory unit-test generation.

### 10.3 Microsoft SQL Server (incl. Azure SQL, Synapse dedicated pools)

**Harvest:** `VIEW DEFINITION`, `VIEW SERVER STATE`, `sys.objects`, `sys.sql_modules`, `sys.dm_exec_query_stats`, Query Store (if enabled), `msdb` (SQL Agent jobs, SSIS catalog `SSISDB`), SSRS ReportServer catalog.

**Conversion highlights**

| SQL Server | Snowflake |
|---|---|
| T-SQL procedures | Snowflake Scripting / JavaScript / Python procedures |
| `#temp` / `##global` tables | Temporary tables |
| `IDENTITY` | `AUTOINCREMENT`/`IDENTITY` |
| `DATETIME` / `DATETIME2` / `DATETIMEOFFSET` | `TIMESTAMP_NTZ` / `TIMESTAMP_TZ` |
| `UNIQUEIDENTIFIER` | `VARCHAR(36)` (+ `UUID_STRING()`) |
| `BIT` | `BOOLEAN` |
| `MONEY` | `NUMBER(19,4)` |
| `CROSS/OUTER APPLY` | `LATERAL` |
| `TOP n` | `LIMIT`/`TOP` |
| SQL Agent jobs | Tasks or external orchestrator |
| SSIS | dbt + orchestrator / Openflow / Matillion etc. |
| SSRS | Power BI paginated / other BI |
| Linked servers | Pipelines / external access |
| CLR assemblies | Java/Python UDFs or redesign |

**Known issues**

| # | Issue | Sev | Fix pattern |
|---|---|---|---|
| MS-01 | Default case-insensitive collation; Snowflake case-sensitive | S1 | Collation policy or normalisation; test joins/filters/GROUP BY |
| MS-02 | `DATETIME` rounding (≈3 ms) vs Snowflake precision | S1 | Reconcile with tolerance; explicit precision |
| MS-03 | `NOLOCK` and isolation hints assume locking model | S4 | Remove; Snowflake uses MVCC-like snapshot semantics |
| MS-04 | Implicit conversions (string↔number, string↔date) | S1 | Explicit casts; parser flags |
| MS-05 | Error handling `TRY/CATCH`, `@@ERROR`, `@@ROWCOUNT`, `RAISERROR` | S2 | Snowflake Scripting exception blocks, `SQLROWCOUNT` |
| MS-06 | Dynamic SQL built from strings | S2 | Static analysis + AI review; `EXECUTE IMMEDIATE` |
| MS-07 | SSIS packages with script tasks (C#) | S2 | Re-engineer; never "convert" script tasks blindly |
| MS-08 | Triggers & cascading FKs enforce integrity | S1 | Snowflake does not enforce PK/FK (except NOT NULL); move to DQ rules + pipeline logic |
| MS-09 | Row-by-row OLTP patterns pointed at the DW | S3 | Hybrid tables only for genuine OLTP-ish needs; otherwise keep OLTP elsewhere |
| MS-10 | Synapse distribution/columnstore tuning emulation | S3 | Remove; measure; cluster only if needed |

**Best practices:** separate **OLTP** SQL Server (stays, feeds Snowflake via CDC) from **analytics** SQL Server (migrates); treat SSIS as a re-engineering stream with its own estimate; inventory SSRS subscriptions — they are business-critical and often forgotten.

### 10.4 Netezza (IBM PureData)
**Harvest:** `_V_TABLE`, `_V_RELATION_COLUMN`, `_V_PROCEDURE`, query history (`_V_QRYHIST`/history DB), nzload scripts.
**Known issues:** distribution keys/zone-map design irrelevant (S3); NZPLSQL procedures (S2); `nzsql` shell orchestration (S2); integer division and date behaviours (S1); end-of-support timelines drive deadline pressure — favour lift-and-shift + refactor backlog.

### 10.5 Amazon Redshift
**Harvest:** `SVV_TABLE_INFO`, `PG_*` catalogs, `STL/SYS` query history, `SVV_EXTERNAL_*` for Spectrum.
**Highlights:** `DISTKEY/SORTKEY` → remove/cluster; `SUPER` → `VARIANT`; Spectrum → external/Iceberg tables; WLM queues → warehouses; stored procedures (PL/pgSQL) → Snowflake Scripting.
**Known issues:** case-folding of identifiers (S2 when quoted identifiers used); `VARCHAR` byte vs char lengths (S2); late-binding views (S2); `UNLOAD` patterns re-pointed (S4). SnowConvert AI provides an end-to-end Redshift path (conversion, data migration, validation) — use it as the default.

### 10.6 Hadoop / Hive / Spark / Impala (Cloudera, HDP, EMR)
**Harvest:** Hive Metastore (read-only DB), HDFS listings (metadata), YARN/Spark history, Oozie/Airflow DAGs, Ranger/Sentry policies.
**Highlights:** HiveQL → Snowflake SQL; Spark (Scala/PySpark) → Snowpark (Snowpark Migration Accelerator assesses API compatibility) or dbt; ORC/Parquet → load or Iceberg; Ranger policies → Snowflake RBAC + masking/row-access policies; Oozie → Tasks/Airflow.
**Known issues:** small-file explosion (S3); schema-on-read data with inconsistent types (S1); Java UDFs/SerDes (S2); Hive partition semantics vs Snowflake micro-partitions (S3); Kerberos-based security model has no direct analogue (S2).
**Best practice:** usually **re-architect**; Iceberg is a strong option where other engines remain.

### 10.7 Databricks / Spark Lakehouse
**Highlights:** Delta → Iceberg (UniForm/conversion) or load; Unity Catalog → Horizon (tags, policies, lineage); notebooks → Snowpark / Snowflake Notebooks; MLflow → Snowflake ML registry or keep cross-platform.
**Known issues:** Python dependency parity in Snowpark (S2); Delta time-travel/semantic differences (S2); job cluster cost models vs warehouse model (S3).
**Positioning note:** Often a *coexistence* conversation rather than full migration — design for interoperability via Iceberg.

### 10.8 Google BigQuery
**Highlights:** `STRUCT/ARRAY` → `OBJECT/ARRAY/VARIANT`; partitioned/clustered tables → clustering where justified; scripting → Snowflake Scripting; policy tags → Snowflake tags + masking.
**Known issues:** nested/repeated field semantics (S1); `SAFE.` functions and error-tolerant casts (`TRY_` equivalents) (S1); slot-based cost models vs credits (S3).

### 10.9 IBM Db2 (LUW, z/OS) & Mainframe Sources
**Highlights:** Db2 SQL PL → Snowflake Scripting; mainframe files (VSAM, sequential) via copybook-driven parsing.
**Known issues:** EBCDIC encoding and code pages (S1); `COMP-3` packed decimals and signed zoned fields (S1); `REDEFINES` and `OCCURS DEPENDING ON` in copybooks (S2); JCL scheduling dependencies (S2); batch windows tied to CICS/IMS (S2).
**Accelerator:** copybook parser → canonical schema → generated conversion + validation rules.

### 10.10 SAP (ECC, S/4HANA, BW/BW4, HANA)
**Known issues:** licensing and contractual limits on extraction methods — SAP has restricted third-party use of certain extraction interfaces (e.g. ODP via RFC), so extraction architecture must be validated with SAP licensing **before** design (S2, commercial); pooled/cluster tables and cryptic table/field names (S2); BW business logic in transformations/ABAP routines (S2); currency/unit conversion and fiscal-calendar logic (S1).
**Best practice:** prefer SAP-sanctioned paths (current SAP–Snowflake integration options, SAP Datasphere/Business Data Cloud routes or certified partner connectors) and rebuild BW semantics in a governed semantic layer.

### 10.11 Greenplum, Vertica, Sybase/SAP ASE & IQ, Exasol
Common themes: distribution/projection design irrelevant (S3); vendor procedural languages (S2); case and NULL semantics (S1); utilities (gpfdist, vsql, bcp) → staged files + `COPY`. SnowConvert AI covers Greenplum and Sybase; verify current coverage for others or route to commercial tools.

### 10.12 OLTP Sources (PostgreSQL, MySQL, operational SQL Server/Oracle)
These are typically **ingestion sources, not migrations**. Pattern: CDC (Openflow, Fivetran, Qlik, Debezium/Kafka, native connectors) → raw/bronze (immutable) → modelled layers. Snowflake Postgres/Hybrid Tables may suit specific operational needs — evaluate per use case, do not default.

### 10.13 Cross-Source Semantic-Drift Checklist (run on every engagement)
1. Case sensitivity (identifiers and data)
2. NULL vs empty string
3. Numeric precision/scale and integer division
4. Date vs timestamp; time-zone policy (`NTZ/LTZ/TZ`)
5. Trailing spaces / CHAR padding
6. Duplicate handling (SET tables, unenforced constraints)
7. Sort order / collation in `ORDER BY`, `MIN/MAX` on strings
8. Nondeterministic `UPDATE…FROM` / `MERGE` with multi-match sources
9. Implicit casts
10. Floating-point aggregation order
11. Session parameters (date formats, week start, `TIMESTAMP_TYPE_MAPPING`)
12. Transaction/commit semantics in procedures (autocommit, DDL implicit commits)

---

## 11. ETL, Orchestration & BI Migration

Conversion tools focus on database code. In practice ETL and BI are where programmes overrun. ALTITUDE treats them as first-class streams.

### 11.1 ETL Tools

| Source ETL | Target options | Approach | Known issues |
|---|---|---|---|
| Informatica PowerCenter | dbt (ELT), Informatica IDMC (re-platform), Matillion, Openflow | Parse XML exports → mapping graph → classify (pass-through / transform / complex) → generate dbt models for SQL-expressible logic | Mapplets, lookups with caches, router/union semantics, session overrides, parameter files; row-by-row expression logic |
| IBM DataStage | dbt, Matillion, Snowpark | Parse DSX/ISX exports | Parallel job partitioning, transformer stage variables, sequence jobs |
| SSIS | dbt + orchestrator, ADF, Openflow | Parse `.dtsx` | Script tasks (C#), event handlers, package configurations |
| Oracle ODI | dbt | Parse repository | Knowledge modules embed SQL dialect |
| Ab Initio | dbt / Snowpark | Graph export (licensing permitting) | Proprietary components, PDL |
| Talend | dbt / Talend on Snowflake | Parse job items | Java routines |
| Hand-coded (shell + SQL, BTEQ, PL/SQL) | dbt + orchestrator | Parser + AI agent | Undocumented control flow, file-system side effects |

**Principles**
- Push transformation **into Snowflake (ELT)**; keep extraction/ingestion tools for what they do well.
- Classify every job: *retire / lift / re-engineer*; target ≥30% retire after usage analysis.
- Generate dbt with conventions (`stg_ / int_ / dim_ / fct_ / agg_`), tests (`unique`, `not_null`, relationships, accepted values) and documentation — generated from the mapping graph, header-stamped.
- Bronze/raw layer is **immutable** (append-only, no updates/deletes); kill-test in CI verifies no DML other than INSERT on bronze objects.

### 11.2 Orchestration & Schedulers

| Source | Target |
|---|---|
| Control-M, Autosys, Tivoli, Oozie, SQL Agent, cron | Snowflake Tasks (+ task graphs), Airflow/Astronomer, Dagster, Prefect, dbt Cloud jobs |

**Known issues:** calendar-based logic (business days, fiscal calendars), cross-system dependencies (file arrivals, upstream SAP jobs), restart/rerun semantics, SLA alerting. **Accelerator:** scheduler-definition parser → dependency DAG → generated task graph or Airflow DAG with SLA and retry policies as data.

### 11.3 BI & Semantic Layer

| Source BI | Approach |
|---|---|
| Tableau | Repoint connections; replace custom SQL with governed views/semantic views; extract-vs-live decision per workbook |
| Power BI | Gateway/DirectQuery vs import decision; repoint; consolidate duplicated measures into certified semantic models |
| MicroStrategy | Re-point warehouse catalog; VLDB settings review; consider semantic layer migration |
| Cognos / Business Objects | Usually rationalise first (often thousands of unused reports), then rebuild top-used content |
| SSRS | Paginated reports in Power BI or alternative |
| Excel/Access shadow BI | Identify via usage logs and access patterns; offer governed replacements |

**Best practices:** usage-based rationalisation before migration (BI estates often contain large shares of unused content); move business logic **out of** BI into Snowflake semantic views/dbt metrics; each certified KPI has exactly one definition (enforced as data); validate dashboards with **visual + numeric** regression (screenshot diff + KPI value diff).

---

## 12. Data Movement, CDC & Validation

### 12.1 Historical Load

| Volume band | Approach |
|---|---|
| < 10 TB | Extract to Parquet/CSV (compressed) → cloud stage → `COPY INTO`; parallelise by table/partition |
| 10–500 TB | Partitioned parallel unload from source, multiple extract agents, file sizing ~100–250 MB compressed, warehouse sized for load waves then suspended |
| > 500 TB / constrained network | Offline transfer appliances (AWS Snowball / Azure Data Box / GCP Transfer Appliance) → object storage → `COPY` |

**Best practices:** load into a **landing schema with lineage columns** (`_source_system`, `_extract_ts`, `_batch_id`, `_row_hash`); never transform during historical load; checkpoint per table/partition for restartability; track credits per load wave.

### 12.2 Incremental & CDC

| Option | Use when |
|---|---|
| Snowflake Openflow connectors | Supported sources, Snowflake-native management preferred |
| Fivetran / HVR, Qlik Replicate, Striim, Oracle GoldenGate, Informatica CDC | Enterprise CDC with existing licences or broad source coverage |
| Debezium + Kafka → Snowpipe Streaming / Kafka connector | Streaming-first, open-source preference |
| Snowpipe (file-based) | Files land in object storage |
| Batch watermark extracts | Sources without log access |

**Known issues:** CDC on tables without primary keys; LOB columns in CDC streams; DDL changes mid-stream; hard deletes vs soft deletes; time-zone of change timestamps; log retention on source shorter than outage windows.

### 12.3 Validation & Reconciliation (Equivalence Evidence)

Validation levels, applied by **table tier** (Tier-1 = regulatory/financial/critical):

| Level | Check | Tier-1 | Tier-2 | Tier-3 |
|---|---|---|---|---|
| L0 | Schema parity (columns, types, nullability, mapped per rules) | ✔ | ✔ | ✔ |
| L1 | Row counts (overall and per partition/date) | ✔ | ✔ | ✔ |
| L2 | Column aggregates: sum, min, max, count distinct, null count, string-length stats | ✔ | ✔ | sample |
| L3 | Row-level hash comparison (keyed, normalised per drift rules) | ✔ | sample | — |
| L4 | Business-output parity: report/KPI values, query-result diffs on top N production queries | ✔ | ✔ | — |
| L5 | Performance parity: top queries p50/p95 vs baseline and SLA | ✔ | ✔ | — |

**Rules:**
- Normalisation rules (trim, case, NULL/empty, timestamp precision, numeric scale) are **data**, versioned, and applied identically on both sides before hashing — otherwise L3 produces false mismatches.
- Thresholds (e.g. 0 mismatches for Tier-1 keys, tolerance for floats) live in the rubric table.
- Row-level validation runs only under the permission-gated validation module with per-dataset authorisation logged; results stored as aggregates + mismatch keys, never full rows in the platform.
- **AI mismatch triage agent:** clusters mismatches by root-cause signature (e.g. "all diffs are trailing spaces in CHAR columns" → TD-03) and links to the Pattern Library fix, with confidence and rationale.
- Use SnowConvert AI's data validation where it covers the source; ALTITUDE adds tiering, normalisation-as-data, triage, evidence packs and sign-off workflow on top.

---

## 13. Cutover, Coexistence & Decommissioning

### 13.1 Cutover Strategies

| Strategy | When | Risk controls |
|---|---|---|
| Big-bang | Small/medium estates, tight coupling | Full dress rehearsal ×2, rollback window, freeze |
| Phased by domain (strangler) | Large estates | Domain-level go/no-go, reverse feeds for unmigrated consumers |
| Parallel run | Regulatory/finance | Daily automated L4 parity reports; exit criteria = N consecutive clean cycles incl. one month-end |
| Consumer-by-consumer | Many downstream apps | Connection registry; virtualisation layer during transition |

### 13.2 Go/No-Go Evidence Pack (auto-generated from snapshots)
- Reconciliation status per table tier, with outstanding mismatches and accepted deviations (each with approver)
- Performance results vs SLA
- Security parity: every legacy grant mapped or intentionally retired; access-review sign-off
- Runbook and on-call readiness; agent fleet health
- Rollback plan, tested; data-freeze and catch-up plan
- Business UAT sign-offs; open defects by severity

### 13.3 Decommissioning
Read-only period → archive (Snowflake or low-cost object storage with documented retention and legal-hold status) → licence/hardware termination evidence → **savings realisation report** (the number the CFO remembers). The platform tracks remaining legacy consumers via source query logs and blocks decommission while active consumers exist.

---

# PART IV — SNOWFLAKE IMPLEMENTATION EXCELLENCE

## 14. Snowflake Well-Architected Baseline (Best Practices)

**Aligned to Snowflake's Well-Architected Framework** (published June 2026), which has five pillars: Security & Governance, Operational Excellence, Reliability, Performance Efficiency and Cost Optimization. The mapping is:
- 14.1–14.3 → Security & Governance
- 14.4 → Performance Efficiency
- 14.5 → Cost Optimization
- 14.6–14.7 → Operational Excellence and Reliability
- 14.8 → the framework's AI and agent guidance across pillars

The same checks power Package D (Section 6) and Package O (Section 7).

Each item below is an automated check in the platform (metadata-only, against `ACCOUNT_USAGE`, `ORGANIZATION_USAGE`, `INFORMATION_SCHEMA`, Trust Center findings), with severity, rationale and remediation stored as data.

### 14.1 Organisation & Accounts
- Use Snowflake **Organizations**; separate accounts (or at minimum databases with strict RBAC) for prod / non-prod; consider separate accounts for regulated data or regions.
- Naming conventions as data: `<ENV>_<DOMAIN>_<LAYER>` databases; schema per layer or per data product.
- Replication & failover groups for DR where RPO/RTO require it; test failover twice a year.

### 14.2 Identity & Access
- SSO via SAML/OIDC; SCIM provisioning; MFA for all human users; key-pair or OAuth/workload identity for services — no passwords for service users.
- **Role hierarchy:** access roles (object privileges) → functional roles (job function) → assigned to users; never grant object privileges directly to users.
- `ACCOUNTADMIN` limited to break-glass users with alerting on use; `SECURITYADMIN`/`SYSADMIN` separation.
- Managed access schemas for production; future grants defined in IaC.
- Separate roles and warehouses for AI agents (distinct machine identities).

### 14.3 Network & Data Protection
- Network policies / network rules on all accounts; PrivateLink / Private Service Connect for regulated clients.
- Tri-Secret Secure / customer-managed keys where required.
- Tag-based masking policies (tag → policy binding) so PII protection is mechanical; row-access policies for entitlement-based filtering.
- Classification via Horizon automatic classification, steward-reviewed.

### 14.4 Compute & Performance
- Warehouses per **workload class** (ELT, BI, data science, ad-hoc, agents) — not per team by default.
- `AUTO_SUSPEND` 60s for most; longer only where cache benefit is measured. `AUTO_RESUME` on.
- Multi-cluster (scale-out) for concurrency; scale-up for complex queries — decide with query-history evidence.
- Query acceleration service and search optimization only where justified by measured workloads.
- Clustering keys only on large tables with demonstrated pruning problems; monitor clustering cost.
- Statement timeouts and queue timeouts per warehouse.

### 14.5 Cost Governance (FinOps)
- Resource monitors on every warehouse + account-level; Snowflake **budgets** for teams/projects.
- Object tagging for cost centre; chargeback/showback from `METERING_HISTORY`, `QUERY_ATTRIBUTION_HISTORY`, `WAREHOUSE_METERING_HISTORY`.
- Storage hygiene: transient tables for re-creatable staging, appropriate Time Travel retention, drop unused clones.
- Serverless feature costs monitored separately (tasks, Snowpipe, dynamic tables, clustering, Cortex).

### 14.6 Data Engineering
- Layering: raw/bronze (immutable) → conformed/silver → curated/gold → semantic/data products.
- Dynamic tables for declarative pipelines; streams + tasks for event-driven logic; Snowpipe/Snowpipe Streaming for ingestion; Openflow for managed connectors.
- dbt (Core or Cloud, or dbt Projects on Snowflake where it fits) with CI; Git integration; schema change via IaC (Terraform provider, schemachange/DCM-style tooling).
- Data contracts at product boundaries; DMFs (data metric functions) on Tier-1 tables.

### 14.7 Observability & Operations
- Central observability database harvesting `ACCOUNT_USAGE` across accounts (multi-account archive pattern) with longer retention than default views.
- Alerts (Snowflake Alerts / external) for failed tasks, credit spikes, long-running queries, login anomalies, privilege escalations.
- Event tables for UDF/procedure logs and traces.
- Release-management watch: track Snowflake behaviour-change bundles and test them in non-prod before enablement.

### 14.8 AI Readiness Baseline
- Column and table comments on Tier-1 objects; semantic views for top KPI domains; Cortex Search services on governed document corpora; agent roles with least privilege; Cortex usage monitored and budgeted. (Detail in Section 19.)

### 14.9 Baseline Check Example (as data)

```yaml
check:
  id: WA-COMP-003
  pillar: compute
  title: "Warehouse auto-suspend exceeds policy"
  query_ref: sql/wa_comp_003.sql          # generated, header-stamped
  threshold_ref: rubric.compute.auto_suspend_max_seconds   # value lives in rubric table
  severity: medium
  rationale: "Idle warehouses accrue credits; most workloads gain little cache benefit beyond 60s"
  remediation:
    auto_fix_available: true
    autonomy: L2            # drafted ALTER for human approval
    playbook: PB-COMP-AUTOSUSPEND
```

---

## 15. Greenfield Implementation Blueprint

### 15.1 "Snowflake Foundation" — 6–10 Weeks

| Week | Workstream outputs |
|---|---|
| 1–2 | Discovery, use-case prioritisation, target architecture ADRs, account/org design, security requirements |
| 2–4 | Landing zone via Terraform: accounts, databases, roles, warehouses, network policies, SSO/SCIM, resource monitors, budgets, tags, masking policy framework |
| 3–5 | Ingestion framework (Openflow/Snowpipe/CDC tool), raw layer conventions, dbt project scaffold, CI/CD |
| 4–7 | First data product end-to-end: source → bronze → silver → gold → semantic view → dashboard and Cortex Analyst |
| 6–8 | Observability & FinOps pack, DQ (DMFs + rules as data), governance (classification, ownership, glossary) |
| 8–10 | Hardening, Well-Architected check run, runbooks, enablement, handover to run service |

### 15.2 Foundation Accelerators (productised IP)
- **Terraform landing-zone modules** (RBAC hierarchy generator from a YAML role model, warehouse catalogue, monitors, network rules, tag/masking framework).
- **Ingestion framework** with metadata-driven pipelines (source registry as data).
- **dbt starter** with naming conventions, macros (audit columns, SCD2, incremental merge), test packs, documentation generation.
- **Observability pack** (multi-account usage archive, dashboards, alerts).
- **Governance pack** (tag taxonomy, classification workflow, policy library).
- **AI pack** (semantic view generator from dbt metrics/KPI registry, Cortex Search templates, agent role template, evaluation harness).

---

# PART V — AI ACCELERATION & AGENTS

## 16. AI Across the Lifecycle

| Phase | AI capability | Human gate | Expected effort reduction (hypothesis — validate per engagement) |
|---|---|---|---|
| Assess | Auto-classify objects (keep/retire/rewrite) from usage + lineage; summarise code modules; complexity scoring; risk narrative | Architect reviews classifications <0.80 confidence | 50–70% of assessment analyst effort |
| Plan | Wave clustering from dependency graph; pattern recommendation; estimate with confidence bands; draft SOW and business case | Delivery lead + sponsor approve | 40–60% |
| Convert | SnowConvert AI as base; agent remediates EWIs/FDMs, refactors procedural code, explains changes, generates unit tests | Peer review on every AI change; mandatory tests pass | 30–60% of remediation effort |
| ETL | Mapping-graph extraction from ETL exports; dbt generation; documentation | Engineer review | 30–50% |
| Validate | Generate reconciliation suites; mismatch root-cause clustering; fix suggestions | Data owner signs off deviations | 40–60% of triage effort |
| BI | Measure deduplication; semantic view generation; report-usage rationalisation | BI owner approves | 30–50% |
| Cutover | Go/no-go pack generation; runbook drafting | Exec approval | 50% of document effort |
| Operate | Agent fleet (Section 18) | Autonomy levels L0–L3 | Ongoing |
| Govern | Description generation, classification suggestions, glossary linking | Steward approval | 60–80% of documentation effort |

**AI engineering rules**
- Every AI-generated artifact stores: prompt/template ID + version, model ID, inputs (by reference), output, confidence, rationale, reviewer, decision, timestamp.
- AI never writes directly to production; outputs land as pull requests or draft changes.
- Client code and metadata sent to an LLM only through approved paths: Snowflake Cortex inside the client account (preferred — data stays in-boundary) or the client's approved model endpoint; configurable per tenant.
- Golden-test corpus per source dialect (input code → expected Snowflake code → expected results on synthetic data) gates any prompt or model change.

## 17. The AI Delivery Partner ("Sherpa") & Specialist Advisors

### 17.1 Sherpa — Behaviour Spec
- Grounded strictly in the engagement snapshot and Pattern Library; cites evidence IDs.
- **Opinionated:** flags risks unprompted, disagrees with plans that contradict evidence, states confidence.
- Knows the current phase, gate criteria, burn-down and blockers; proposes the next three actions daily.
- Available in the portal, Slack/Teams, and via MCP in Claude, Cursor, Cortex Code or Copilot.

### 17.2 Specialist Advisors

| Advisor | Expertise | Typical outputs |
|---|---|---|
| Teradata Advisor | BTEQ/SPL/TPT, SET/case semantics | BTEQ conversion plans, dedupe strategy |
| Oracle Advisor | PL/SQL packages, NLS, numeric policy | Package decomposition designs |
| SQL Server Advisor | T-SQL, SSIS, SSRS, Agent | SSIS re-engineering plans |
| Hadoop/Spark Advisor | Hive, Spark, Ranger | Snowpark/Iceberg designs |
| ETL Advisor | Informatica/DataStage/ODI | Mapping classification, dbt designs |
| Snowflake Architect | Well-Architected, Iceberg, DR | ADRs, landing zone reviews |
| FinOps Advisor | Credits, warehouses, serverless costs | Cost forecasts, rightsizing plans |
| Security Advisor | RBAC, policies, network, compliance | Role models, policy designs |
| Governance & DQ Advisor | Classification, ownership, DMFs | Governance operating model |
| Cortex/AI Advisor | Semantic views, Cortex Search/Agents | AI-readiness plans, agent designs |

### 17.3 Architecture Review Board (multi-perspective decision review)
One decision → seven lenses (CFO, CISO, Platform Architect, Data Steward, Delivery Lead, Business Owner, Snowflake Account Team) → each states its key question, concerns and vote → synthesised recommendation with **dissent recorded**. Stored as an ADR with evidence links. Humans make the decision; the board makes it better-informed.

### 17.4 Executable Skills (initial set)
`run_assessment` · `classify_objects` · `recommend_pattern` · `plan_waves` · `estimate_wave` · `convert_module` · `remediate_ewis` · `generate_unit_tests` · `generate_dbt_from_mapping` · `generate_reconciliation_suite` · `triage_mismatches` · `generate_rbac_from_legacy_grants` · `run_well_architected_check` · `draft_sow` · `draft_business_case` · `build_go_no_go_pack` · `generate_board_pack` · `score_ai_readiness`.

## 18. Agentic Run-Operations Fleet (Maintenance Agents)

### 18.1 Autonomy Levels
- **L0** observe & report · **L1** recommend · **L2** draft change for human approval · **L3** execute pre-approved, reversible, scoped actions with audit and auto-rollback.
- Default for new clients: L1–L2. L3 only for actions listed in the client's **pre-approved action catalogue** (data), each with blast-radius limits.

### 18.2 Agent Catalogue

| # | Agent | Trigger | What it does | Max autonomy | Guardrails | KPI |
|---|---|---|---|---|---|---|
| 1 | **Cost Sentinel** | Hourly | Detects credit anomalies by warehouse/user/query pattern; forecasts month-end; explains spikes | L1 | Read-only | Forecast error; anomalies caught before invoice |
| 2 | **Warehouse Rightsizer** | Daily | Recommends size/cluster/auto-suspend changes from load and queue metrics | L3 (auto-suspend only) / L2 (size) | Change window; auto-revert if queueing rises | Credits saved; SLA breaches = 0 |
| 3 | **Query Performance Doctor** | On regression | Detects plan/runtime regressions on top queries; suggests rewrite, clustering, QAS, search optimization | L2 | Tests on clone before proposing | p95 runtime trend |
| 4 | **Pipeline Triage** | Task/dbt failure | Reads error, logs, recent changes; classifies root cause; drafts fix or reruns idempotent jobs | L3 (rerun idempotent) / L2 (fix) | Idempotency flag as data | MTTR |
| 5 | **Schema Drift Guard** | Source change | Detects upstream schema changes via CDC/metadata; assesses downstream impact via lineage; drafts contract/version update | L2 | Contract rules | Breaks prevented |
| 6 | **DQ Incident Agent** | DMF/rule failure | Clusters failures, finds probable cause, notifies owner, opens incident, drafts quarantine | L2 | Never deletes data | Detection lead time vs consumer discovery |
| 7 | **Access Hygiene Agent** | Weekly | Finds dormant users/grants, direct grants, over-privileged roles, ACCOUNTADMIN usage; drafts revocations; runs access reviews | L2 | Owner approval required | Dormant grants; review completion |
| 8 | **Security Posture Agent** | Daily | Tracks Trust Center/CIS benchmark findings, MFA gaps, network policy gaps, unusual login patterns | L1 | Escalates to SOC | Open critical findings |
| 9 | **Storage & Object Pruner** | Weekly | Finds unused tables, stale clones, excessive Time Travel, orphaned stages | L2 | Archive-before-drop; legal-hold check | Storage TB/cost reduced |
| 10 | **Release Change Watcher** | On new behaviour-change bundle / release notes | Maps announced changes to client usage (functions, syntax, settings) and runs impacted tests in non-prod | L1 | — | Upgrade incidents = 0 |
| 11 | **Documentation & Catalog Agent** | On object create/change | Drafts table/column descriptions, glossary links, ownership suggestions | L2 | Steward approval | Description coverage on Tier-1 |
| 12 | **Classification Agent** | On new columns | Proposes sensitivity tags; verifies tag propagation through lineage; flags unmasked PII | L2 (tag) / L1 (policy) | Privacy approval | Unprotected classified columns = 0 |
| 13 | **Lineage Gap Agent** | Weekly | Finds Tier-1 objects without resolvable upstream lineage | L1 | — | Lineage coverage % |
| 14 | **SLA Forecaster** | Continuous | Predicts late data deliveries from upstream timings | L1 | — | Late deliveries warned |
| 15 | **Cortex Cost & Quality Monitor** | Daily | Tracks AI function/agent spend, latency, groundedness and eval drift | L1 | — | Cost per accepted answer |
| 16 | **Semantic Model Steward** | On dbt/KPI change | Keeps semantic views in sync with certified KPI definitions; detects duplicate KPI definitions | L2 | Owner approval | KPI definition conflicts |

### 18.3 Agent Implementation Pattern
- Built on **Cortex Agents** inside the client account where possible (data stays in-boundary), with tools implemented as stored procedures/UDFs over `ACCOUNT_USAGE` and the observability database; MCP exposure for external clients.
- Each agent: distinct service user + role; tool scope minimal; every run logged (inputs, tool calls, output, decision, approver) to an immutable agent-action table.
- Rules, thresholds, schedules and pre-approved action catalogue stored as data per tenant.
- Agents read from the Package O observability data product (Section 7): one telemetry foundation for diagnostics, observability and operations.
- Evaluation suite per agent (golden incidents) run on every prompt/model change; regression blocks promotion.

## 19. AI-Ready Platform Module

Reuses the EAIRN readiness framework (eight pillars: Data Quality, Governance, Metadata, Security, AI Engineering, Semantic Layer, Agent Readiness, RAG Readiness) as the scoring engine, with Snowflake-specific checks.

### 19.1 Snowflake AI-Readiness Checks (examples)
- **Metadata:** comment coverage on Tier-1 columns; tag coverage; glossary linkage.
- **Semantic layer:** semantic views covering top KPI domains; one definition per KPI; verified queries/synonyms present.
- **RAG:** Cortex Search services over governed corpora; source ACLs reflected in search filters; refresh SLAs.
- **Agent readiness:** agents run under distinct roles; no agent holds write privileges without approval workflow; action audit reconstructable.
- **Security:** classified columns 100% masked; row-access policies on entitlement-sensitive tables.
- **Quality:** DMFs attached to Tier-1 tables; freshness SLAs measured.

### 19.2 AI-Ready Programme (12 weeks)
1. Score (EAIRN-style snapshot) → 2. Fix foundations (descriptions, classification, masking) → 3. Build semantic views for 3–5 KPI domains → 4. Stand up Cortex Analyst + Search + one Cortex Agent with evaluation harness → 5. Launch in Snowflake Intelligence for a pilot group → 6. Re-score and publish the delta.

### 19.3 Use-Case Packs (vertical accelerators)
Utilities & energy first (founder depth): AMI consumption analytics, outage impact, asset health, vegetation management, procurement spend, customer churn/arrears, regulatory reporting assistants. Then banking, insurance, healthcare, retail packs. Each pack = data model, dbt models, semantic view, Cortex Agent spec, demo questions with golden answers, value case template.

---

# PART VI — ADJACENT SERVICE STREAMS

## 20. Stream Prioritization

Not every stream is equally important to a migration startup. Ranked by *attach rate to migrations × client pain × recurring-revenue potential × fit with platform*:

| Rank | Stream | Why it matters | Attach point |
|---|---|---|---|
| 1 | **FinOps / cost governance** | Every Snowflake customer worries about cost; fastest ROI story; recurring | Foundation + run service |
| 2 | **Data quality & validation** | Migration success depends on it; post-migration trust | Validation → DQ run service |
| 3 | **Security & access governance** | Gate to go-live in regulated industries; RBAC is always messy | Foundation |
| 4 | **Data governance (Horizon, catalog, classification, ownership)** | Prerequisite for AI; audit pressure | AI-ready programme |
| 5 | **Observability** | Productised as Package O; underpins run service and agents | Add-on to Package D, migrations and Managed Run |
| 6 | **Semantic layer & data products** | Unlocks Cortex Analyst/agents and self-service | AI-ready programme |
| 7 | **AI/Cortex use cases** | Expansion revenue, executive attention | Post-migration |
| 8 | **DataOps / CI/CD** | Delivery velocity, change safety | Foundation |
| 9 | **MDM & reference data** | Important, but long cycles; partner rather than build | Selectively |
| 10 | **Data sharing, clean rooms, Native Apps** | Monetisation & ecosystem plays | Selectively, vertical-specific |
| 11 | **Change management & enablement** | Adoption risk is real; often under-scoped | Every engagement |

## 21. Data Governance
**Scope:** operating model (owners, stewards, councils), tag taxonomy and classification, policy library (masking, row access, projection, aggregation policies), ownership coverage, glossary, catalog integration (Horizon catalog; Collibra, Alation, Atlan, Purview, DataHub sync), access reviews, retention and legal hold, AI governance (agent registry, model inventory, EU AI Act/NIST AI RMF alignment where applicable).
**Accelerators:** tag taxonomy templates per industry; policy-as-code library; ownership bootstrapping from query history (top consumers/producers suggested as owners with confidence); cross-tool consistency checks (catalog PII ↔ Snowflake tags).
**Key metrics:** owner coverage on Tier-1; classified-but-unprotected columns (target 0); access-review completion; glossary liveness.

## 22. Data Quality
**Scope:** rules as data (completeness, validity, uniqueness, freshness, consistency, accuracy), DMFs (system and custom) on Tier-1 tables, dbt tests, contract-based checks, incident workflow with MTTR, DQ scorecards per data product.
**Accelerators:** rule generator from profiling **metadata** (and permission-gated samples where authorised); migration-reconciliation rules promoted to permanent DQ rules after cutover; integration adapters for Monte Carlo, Soda, Great Expectations, Anomalo, Informatica DQ.
**Principle:** DQ rules never hardcoded in pipeline code; hardcoded-only rule estates cap the DQ score.

## 23. Observability
Productised as **Package O (Section 7)**. It includes a multi-account archive kept longer than the native views, an ~80-KPI catalogue, cost, performance, security and AI dashboards, event-table tracing via Snowflake Trail, pipeline SLA tracking, alerting into PagerDuty, ServiceNow, Slack or Teams, and an ask-the-platform agent. A self-serve O1 Native App is a later Marketplace lead-generation play.

## 24. FinOps
Cost baselining, unit economics (cost per query, per data product, per dashboard, per agent answer), chargeback/showback by tag, budget and monitor design, commitment/capacity planning, serverless and Cortex cost tracking, quarterly optimisation sprints. Commercial option: **gain-share** (fee = % of verified savings, capped) — strong door-opener for existing Snowflake customers. Entry is through Package D domain D1; continuous control comes through Package O.

## 25. Security
Landing-zone hardening, RBAC redesign (legacy grant mapping → role model generator), network and private connectivity, key management, Trust Center/CIS benchmark remediation, SIEM integration (login/access history), privileged access workflows, agent identity model, compliance evidence packs (SOX, HIPAA, PCI, NERC CIP-adjacent controls for utilities, GDPR).

## 26. Metadata, Semantic Layer & Data Products
KPI registry with one definition per KPI; semantic views generated from dbt metrics/KPI registry; data product manifests (YAML) with contracts, owners, SLAs, endpoints (SQL, REST, MCP); internal listings/Marketplace for distribution — integrates with the MERIDIAN marketplace specification as the downstream consumption layer.

## 27. MDM, Sharing, Clean Rooms & Native Apps
MDM: partner with established MDM vendors; provide Snowflake-side integration patterns and match/merge quality checks. Sharing: secure data sharing, listings, cross-region replication. Clean rooms: Snowflake Data Clean Rooms for retail/media/finance partnerships. Native Apps: package ALTITUDE accelerators (FinOps Sentinel, AI-Readiness Scorer, Migration Assessment) as Marketplace apps.

## 28. DataOps & Change Management
Git-based workflows, environments via zero-copy clones, CI (lint, unit tests, dbt tests, policy checks), CD with approvals, Terraform state management, release calendars. Change management: role-based enablement paths, champions network, office hours, adoption telemetry tied to the value case.

---

# PART VII — PLATFORM ENGINEERING

## 29. Reference Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ EXPERIENCE   Portal (Next.js) · Sherpa chat · Advisors · Review Board     │
│              Progress boards · Evidence drill-through · Board-pack export │
├──────────────────────────────────────────────────────────────────────────┤
│ ACCESS       REST /api/v1 · MCP server · Slack/Teams bots · Webhooks      │
│              OIDC SSO · RBAC (Exec, Delivery Lead, Engineer, Steward,      │
│              Client Viewer, Partner Admin)                                │
├──────────────────────────────────────────────────────────────────────────┤
│ SERVICES     Assessment · Pattern Recommender · Wave Planner · Estimator  │
│              Conversion Orchestrator (SnowConvert AI + agents)            │
│              ETL/BI Converters · Load & CDC Orchestrator · Validation     │
│              Cutover · Well-Architected Checker · AI-Readiness Scorer     │
│              Agent Fleet Runtime · Workflow & Approvals · Evidence Store   │
├──────────────────────────────────────────────────────────────────────────┤
│ KNOWLEDGE    Pattern Library (mappings, known issues, fixes, tests)       │
│              Rubrics (scoring, estimation, gates, thresholds)              │
│              Golden-test corpus per dialect · Playbooks                   │
├──────────────────────────────────────────────────────────────────────────┤
│ DATA         Postgres (control plane) or Snowflake (native edition)       │
│              Object store (artifacts, snapshots) · Vector index (search)  │
├──────────────────────────────────────────────────────────────────────────┤
│ CONNECTORS   Teradata · Oracle · SQL Server · Netezza · Redshift · Hive   │
│              Databricks · BigQuery · Db2 · SAP · Greenplum · Sybase       │
│              Informatica · DataStage · SSIS · ODI · Control-M · Autosys   │
│              Tableau · Power BI · MicroStrategy · Cognos · BO             │
│              Git · Jira/ServiceNow · Slack/Teams · Catalogs · DQ tools    │
├──────────────────────────────────────────────────────────────────────────┤
│ CLIENT       Source systems (read-only) · Snowflake target account(s)     │
│ BOUNDARY     Row data never leaves the client boundary                     │
└──────────────────────────────────────────────────────────────────────────┘
```

### 29.1 Deployment Editions
| Edition | Where it runs | For |
|---|---|---|
| **Native** | Snowflake Native App + Snowpark Container Services in the client account | Regulated clients; strongest security review |
| **Hybrid** | Control plane SaaS (metadata only) + extraction agents in client network | Most clients |
| **Partner** | Multi-tenant SaaS, white-labelled via theme tokens | SIs and independents |

### 29.2 Extraction Agent
A lightweight container deployed inside the client network: connects read-only to sources, harvests metadata/code/query logs, runs unloads and row-level validation **locally**, and ships only metadata, aggregates, hashes and mismatch keys to the control plane. Published permission manifest per source; CI kill-test proves no write capability.

### 29.3 Technology Stack
| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router), TypeScript, Tailwind, shadcn/ui, Recharts, D3 (dependency graphs) |
| API | FastAPI (Python — strongest parser/data ecosystem), OpenAPI 3.1, generated SDKs |
| Workflow | Temporal (durable approvals, long-running loads, retries) |
| Parsing | SnowConvert AI CLI as primary converter; sqlglot for analysis/normalisation; ANTLR grammars where needed; ETL export parsers per tool |
| LLM | Snowflake Cortex (in-account) default; tenant-configurable external endpoints (Anthropic Claude etc.) via approved gateway |
| Data | PostgreSQL 16 + pgvector (SaaS) / Snowflake tables (Native) |
| IaC/CI | Terraform (incl. Snowflake provider), GitHub Actions, dbt |
| Observability | OpenTelemetry |

## 30. Canonical Data Model

### 30.1 Entity Groups
| Group | Entities |
|---|---|
| Engagement | tenant · client · engagement · phase · gate · decision (ADR) · raid_item |
| Estate | source_system · source_object (table/view/proc/function/macro/script/job/report) · object_version · column · dependency_edge · usage_stat · grant |
| Classification | object_disposition (keep/retire/rewrite) · complexity_score · tier · sensitivity_tag |
| Planning | wave · wave_object · pattern_recommendation · estimate · estimate_factor |
| Conversion | conversion_run · converted_artifact · conversion_issue (EWI/FDM) · ai_change · review |
| Movement | load_job · load_partition · cdc_stream |
| Validation | validation_suite · validation_check · validation_run · mismatch_cluster · accepted_deviation |
| Cutover | cutover_plan · rehearsal · go_no_go · rollback_plan |
| Run | agent · agent_version · agent_run · agent_action · approval · incident |
| Knowledge | pattern (mapping) · known_issue · fix_pattern · test_case · playbook · rubric · rubric_version |
| Audit | audit_event · snapshot |

### 30.2 Key Invariants
- Every `converted_artifact` links to its `source_object` version, `conversion_run`, all `ai_change`s and a `review` before it may be promoted.
- Every `ai_change` has confidence, rationale, model ID, prompt template version; <0.80 requires named reviewer.
- `snapshot` rows are append-only; a gate decision references a snapshot ID.
- `accepted_deviation` requires a data-owner approver and expiry/review date.
- Estimates reference the `rubric_version` used — re-running an estimate on the same snapshot + rubric reproduces it exactly.

### 30.3 Selected DDL

```sql
CREATE TABLE source_object (
  object_id        VARCHAR PRIMARY KEY,
  engagement_id    VARCHAR NOT NULL,
  source_system_id VARCHAR NOT NULL,
  object_type      VARCHAR NOT NULL,   -- table|view|procedure|function|macro|script|etl_job|schedule|report
  fq_name          VARCHAR NOT NULL,
  code_hash        VARCHAR,            -- for change detection between harvests
  loc              INTEGER,
  last_used_at     TIMESTAMP,          -- from query/usage logs
  usage_90d        INTEGER,
  disposition      VARCHAR,            -- keep|retire|rewrite (AI-proposed, human-confirmed)
  disposition_conf NUMERIC(4,3),
  disposition_rationale VARCHAR,
  tier             VARCHAR,            -- tier1|tier2|tier3
  complexity_score NUMERIC(5,2),
  harvested_at     TIMESTAMP NOT NULL
);

CREATE TABLE known_issue (
  issue_id         VARCHAR PRIMARY KEY,   -- e.g. TD-01
  source_dialect   VARCHAR NOT NULL,
  title            VARCHAR NOT NULL,
  severity         VARCHAR NOT NULL,      -- S1..S4
  detection_rule   VARCHAR NOT NULL,      -- reference to executable detector
  fix_pattern_id   VARCHAR,
  test_case_ids    VARCHAR[],
  frequency_observed INTEGER DEFAULT 0,   -- grows across engagements (anonymised)
  last_verified    DATE NOT NULL,         -- against current Snowflake docs/behaviour
  verified_by      VARCHAR NOT NULL
);

CREATE TABLE ai_change (
  change_id        VARCHAR PRIMARY KEY,
  artifact_id      VARCHAR NOT NULL,
  agent_id         VARCHAR NOT NULL,
  model_id         VARCHAR NOT NULL,
  prompt_template  VARCHAR NOT NULL,      -- id@version
  diff             TEXT NOT NULL,
  confidence       NUMERIC(4,3) NOT NULL,
  rationale        TEXT NOT NULL,
  linked_issue_ids VARCHAR[],
  tests_generated  VARCHAR[],
  reviewer         VARCHAR,               -- required before promotion
  decision         VARCHAR,               -- approved|rejected|modified
  decided_at       TIMESTAMP
);

CREATE TABLE validation_run (
  run_id           VARCHAR PRIMARY KEY,
  suite_id         VARCHAR NOT NULL,
  object_id        VARCHAR NOT NULL,
  level            VARCHAR NOT NULL,      -- L0..L5
  normalisation_rule_version VARCHAR NOT NULL,
  threshold_rubric_version   VARCHAR NOT NULL,
  result           VARCHAR NOT NULL,      -- pass|fail|accepted_deviation
  metrics          JSONB NOT NULL,        -- aggregates only; no row data
  mismatch_key_ref VARCHAR,               -- pointer to in-boundary storage
  executed_in      VARCHAR NOT NULL,      -- client_agent|snowflake
  completed_at     TIMESTAMP NOT NULL
);
```

## 31. Knowledge Base as Data (Pattern Library)

The Pattern Library is the company's core IP. Structure:

```
knowledge/
  dialects/
    teradata/  mappings.yaml  known_issues.yaml  fixes/  tests/
    oracle/    ...
    sqlserver/ ...
  etl/         informatica.yaml  datastage.yaml  ssis.yaml  odi.yaml
  schedulers/  controlm.yaml  autosys.yaml  sqlagent.yaml
  bi/          tableau.yaml  powerbi.yaml  microstrategy.yaml  cognos.yaml
  anti_patterns/ procedural_loops.yaml  full_reload.yaml  over_clustering.yaml
  well_architected/ checks/*.yaml
  rubrics/     pattern_recommender.yaml  estimation.yaml  gates.yaml  validation_thresholds.yaml
  playbooks/   *.yaml
```

**Lifecycle of a pattern entry:** proposed (from an engagement, by human or agent) → reviewed by a practice lead → test case added (input, expected output, synthetic data, expected result) → published with `last_verified` → re-verified on each Snowflake behaviour-change bundle by the Release Change Watcher → deprecated when obsolete.

**Anti-pattern detector** (from the Pattern Library) scores every object: row-by-row loops, `SELECT *` in pipelines, full reloads of large tables, nested views > N levels, cross-joins, non-sargable predicates, unnecessary `DISTINCT`, over-wide `VARIANT` scans — each with estimated credit impact.

## 32. Estimation Engine

Estimates are produced from harvested evidence × factors stored as data, with confidence bands — never a single number.

```yaml
estimation_rubric:
  version: 1.0.0
  unit_effort_hours:            # baseline per object after automated conversion
    table_ddl: 0.1
    view_simple: 0.25
    view_complex: 1.5
    procedure_per_100_loc: { low: 1.5, med: 4, high: 10 }    # by complexity band
    bteq_script_per_100_loc: { low: 1, med: 3, high: 8 }
    etl_job: { passthrough: 1, transform: 6, complex: 24 }
    report: { repoint: 0.5, rebuild: 8 }
  multipliers:
    s1_issue_density: { per_issue: 0.5 }       # hours per S1 occurrence
    test_coverage_absent: 1.3
    dynamic_sql_share: { threshold_ref: rubric.dynamic_sql_high, factor: 1.25 }
    ai_acceleration: { conversion: 0.6, test_generation: 0.5, documentation: 0.3 }  # validated per engagement
  fixed_activities_weeks:
    foundation: { small: 4, medium: 6, large: 10 }
    parallel_run_cycles: 2
  output:
    p50_hours: computed
    p80_hours: computed
    confidence: computed_from_data_completeness
    rationale: required
```

All figures above are **initial seed values to be calibrated** against actuals from the first 3–5 engagements; calibration history is stored with sample sizes and dates. The `ai_acceleration` factors in particular are hypotheses until measured.

## 33. Security, Tenancy & Compliance of the Platform Itself
- SOC 2 Type II within 12–18 months of launch (enterprise buyers will require it); ISO 27001 later.
- Tenant isolation: logical (row-level security on `tenant_id`) for SaaS; physical for Native edition.
- Secrets in a managed vault; source credentials never stored in the control plane for Native/Hybrid editions (held by the in-network agent).
- LLM data handling documented per tenant: model endpoints used, retention (zero-retention endpoints only), regions.
- Full audit of every human and agent action; exportable evidence packs.
- Prompt-injection defence: source code, comments and documents treated as data, never instructions; agent tool scopes enforce least privilege regardless of model output.

---

# PART VIII — COMMERCIAL & STARTUP PLAN

## 34. Service Catalog & Pricing Shapes

Indicative shapes — calibrate to market and region. Fixed-scope offers sell faster for a new firm than T&M.

| Offer | Scope | Duration | Pricing shape (indicative; hypotheses) |
|---|---|---|---|
| **D0 Diagnostics Snapshot** | Automated, in-account D1–D5 checks; top-10 findings; 1-hour readout | 1 week | Free (lead generation) |
| **Package D — Platform Deep Diagnostics** (D1 / D2 / D3) | Section 6 | 2–6 weeks | $20–150K by tier; fee credit; optional value floor |
| **Package O — Platform Observability add-on** (O1 / O2 / O3) | Section 7 | 3–8 weeks onboarding, then ongoing | Setup $15–60K + $3–25K/month, flat by spend band |
| **Remediation Sprint** | Implements accepted Package D suggestions: quick wins, then strategic items | 4–8 weeks | Fixed; optional gain-share on verified savings |
| **BI Rationalisation Programme** | Report rationalisation, KPI lineage, certified semantic layer, retire/merge execution | 6–12 weeks | Fixed by estate size |
| **Migration Assessment** | Full estate harvest, disposition, waves, pattern, estimate with confidence bands, TCO/business case | 3–6 weeks | Fixed fee by estate size (check Snowflake co-funding) |
| **Migration Sprint (mid-market)** | One source, up to N objects: foundation, migrate, validate, cut over | 8–16 weeks | Fixed price per object band; outcome milestones |
| **Migration Factory (enterprise)** | Multi-wave programme | 6–24 months | Fixed price per wave + platform fee |
| **Snowflake Foundation (greenfield)** | Landing zone + first data product, with Package O Core from day one | 6–10 weeks | Fixed |
| **AI-Ready Programme** | Score → fix → semantic views → Cortex agent pilot | 10–12 weeks | Fixed |
| **Governance & DQ Programme** | Operating model, classification, policies, DMFs, catalog | 8–16 weeks | Fixed / phased |
| **Managed Run Service** | Package O3 + L2/L3 support + quarterly optimisation | Annual | Subscription by spend band |
| **Enablement / Academy** | Role-based training, certification preparation | Ongoing | Per seat / cohort |
| **Staff augmentation** | Snowflake engineers and architects | Flexible | T&M; keep below 15% of revenue (low margin, no IP) |

## 35. Go-to-Market & Snowflake Partnership

### 35.1 Snowflake Partner Network
- Join the Snowflake Partner Network as a services partner; progress tiers by certifications (SnowPro Core/Advanced), customer references and sourced/influenced consumption.
- Pursue migration-specific partner designations/competencies and migration incentive programmes (verify current programme names and funding rules with the partner team — these change annually).
- Publish Native Apps on Snowflake Marketplace (D0 Snapshot, then a self-serve Package O1 and the AI-Readiness Scorer) — visibility to account teams and customers.
- Build relationships with regional Snowflake account executives and solution engineers: they control referrals. Bring them consumption-accelerating deals.

### 35.2 Channels
| Channel | Motion |
|---|---|
| Snowflake account teams | Co-sell; Package D positioned as "efficiency that funds new workloads (AI, migrations)", not as cost-cutting; assessments co-funded where programmes allow |
| Direct — vertical | Utilities & energy first (founder network, regulatory depth), then banking/insurance |
| Legacy-renewal signals | Target Teradata/Netezza/Exadata contract renewal windows 12–24 months out |
| Partner edition | Small SIs and independent consultants use the white-labelled platform |
| Content | Pattern-library-backed technical content ("12 ways your Teradata migration silently changes answers"), open-source drift checker, conference talks (Snowflake Summit, BUILD, data user groups) |
| Marketplace | D0 Snapshot Native App → Package D → Package O |

### 35.3 Ideal First Customers (design partners)
3 design partners at discounted rates, in exchange for case studies, calibration data and product feedback:
- two existing Snowflake customers taking Package D followed by Package O, at least one of them a utility;
- one mid-market SQL Server or Oracle migration, starting in phase 2.

## 36. Company Build Plan (0–24 months)

| Phase | Months | Goals | Team | Exit criteria |
|---|---|---|---|---|
| **0 — Foundation** | 0–3 | Legal and IP clearance; entity; partner registration and certifications; D0 Snapshot and Package D v1 (domains D1–D6), built clean-room; Package O Core KPI tier; 1 paid design-partner diagnostic | Founder + 1 senior engineer | First paid Package D delivered, with a measured findings register |
| **1 — Diagnose & Observe** | 3–9 | 3 design partners; Package D v2 (all 10 domains incl. BI layer); Package O tiers O1–O2; remediation sprints; open-source drift checker | 4–7 | 5+ diagnostics; 3 Package O subscriptions; 2 case studies with realised value |
| **2 — Operate & Migrate** | 9–15 | Managed Run (O3 + agent fleet v1); Migration Assessment and Sprint (SQL Server/Oracle first); validation engine; SOC 2 Type I; partner tier upgrade; D0 Snapshot as a Marketplace Native App | 10–18 | ≥3 run clients; first migration cutover with an evidence pack; calibrated estimation factors |
| **3 — Platform & Scale** | 15–24 | Migration Factory (Teradata/Netezza), AI-Ready packs, Native edition, partner/white-label edition, second vertical, first benchmark report; SOC 2 Type II | 18–35 | Recurring revenue ≥30% of total; platform revenue ≥15% |

**Funding options:** bootstrap via services cash flow (recommended initially — services businesses are fundable by customers), then seed round once platform and run revenue are proven, positioning as "AI-native Snowflake services platform". Consider Snowflake Ventures relationships later.

**Hiring priorities:** (1) Snowflake architect with migration delivery scars, (2) parser/compiler-minded engineer (sqlglot/ANTLR), (3) AI engineer for agents and evaluations, (4) delivery lead, (5) partner/alliance manager.

## 37. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Snowflake expands first-party tooling (SnowConvert AI, PS, migration agents) into your value zone | High | High | Wrap, don't compete; differentiate on end-to-end delivery, ETL/BI, validation evidence, run service, vertical depth; stay close to Snowflake roadmap |
| Services startup can't win enterprise trust | High | High | Vertical focus, design partners, founder's Big-4 credibility, fixed-price outcome offers, SOC 2 early |
| AI acceleration claims don't materialise | Medium | High | Measure everything; publish only calibrated factors; human gates protect quality |
| LLM data-handling concerns block deals | Medium | High | Cortex-in-account default; Native edition; zero-retention endpoints; metadata-only by default |
| Key-person dependency | High | Medium | Pattern Library as data; playbooks; pairing |
| Employment/IP conflicts with current employer | Medium | High | Review employment contract, non-compete, non-solicit and IP-assignment clauses with counsel **before** building or approaching clients; build only on own time and equipment |
| Trademark issues with "Snow"-based names | Medium | Medium | Clear brand name early with counsel |
| Price competition from offshore SIs | High | Medium | Sell outcomes, speed and evidence, not hours |
| Cash flow (fixed-price overruns) | Medium | High | Assessment-first; milestone billing; estimation confidence bands priced in |
| Snowflake's free WAF tooling commoditises health checks | High | Medium | Use it as an input to Package D; differentiate on quantification, BI-layer depth, root-cause clustering, remediation-as-code and the suggestion-to-value loop (Sections 6–7) |
| **Prior-employer IP in the founder's accelerators** (BI rationalisation, KPI lineage, observability framework, agent designs) | High | High | Treat them as know-how only. Rebuild clean-room on personal time and equipment, with no copied code, configuration, documents, KPI lists or client data. Get written IP clearance and keep a provenance log per module. Use case studies only with written permission |
| Exposure from guarantees (value floor, fee credit) | Medium | Medium | Apply only above qualification thresholds; cap credits at the fee; define "identified opportunity" in the contract |
| Package O churn once savings are captured | Medium | Medium | Broaden value beyond cost (security, reliability, AI usage, chargeback); flat pricing by spend band; quarterly reviews that surface new value |
| Snowflake account-team ambivalence about cost-reduction work | Medium | Medium | Frame savings as "efficiency that funds new workloads (AI, migrations)"; share pipeline of expansion workloads with AEs |

## 38. Build Plan for Claude Code (BUILD.md Milestones)

Each milestone has testable acceptance criteria. CI-enforced constraints apply throughout: no thresholds in app code; generated files header-stamped and regeneration produces no diff; kill-tests on connectors; snapshots append-only; every AI output stores confidence + rationale.

**Build order (v1.1):** M0 → M1 → **MD → MO** → M7 → M10 (agents on top of Package O) → M2–M6 (migration engine) → M8, M9, M11, M12. Diagnostics and observability ship first because they fund the company.

### M0 — Repository & Canonical Model
- [ ] Monorepo (`portal/`, `services/`, `connectors/`, `knowledge/`, `generated/`, `agents/`, `tests/`, `skills/`)
- [ ] Canonical model migrations (Section 30); YAML schema + validator for knowledge files
- **Accept:** malformed knowledge YAML fails with precise error; CI lint fails on numeric literals in threshold positions

### M1 — Pattern Library v0
- [ ] Teradata, Oracle, SQL Server mappings + known issues from Section 10 encoded as YAML with detectors and test cases
- **Accept:** each S1 issue has an executable detector and at least one golden test passing on synthetic data

### MD — Diagnostics Engine (Package D) *(build immediately after M1)*
- [ ] Access bootstrap script using `SNOWFLAKE` database roles; permission manifest; credit-capped diagnostics warehouse
- [ ] Check catalogue (Section 6.4) as YAML with SQL detectors, value models and remediation templates; thresholds by rubric reference
- [ ] Suggestion engine: root-cause clustering, value model, remediation generator with rollback, Cortex narrative with confidence and rationale, review queue
- [ ] Scorecard for 10 domains with WAF-pillar roll-up; Platform Health Index
- [ ] Exports from one sealed snapshot: findings register (CSV/XLSX), Jira/ADO backlog, remediation PR pack, readout deck
- **Accept:** the same snapshot and rubric version reproduce identical scores and values. Every suggestion has evidence refs, value method, confidence and rollback. The harness runs without ACCOUNTADMIN. On a synthetic account with seeded issues, at least 90% of issues are detected with at most 10% false positives.

### MO — Observability Pack (Package O)
- [ ] Config-driven multi-account harvest (sources, schedules, load strategies as data)
- [ ] Immutable RAW archive (kill-test: no UPDATE/DELETE), CURATED model, KPI dynamic tables, semantic views
- [ ] Core KPI tier, dashboards 1/2/4, alerts with routes and runbooks as data, Cortex Agent over the semantic views
- [ ] Suggestion-to-value tracking that links Package D `kpis_to_watch` to before/after measurement
- **Accept:** history is retained beyond the source retention window in a test. Cost KPIs reconcile to Snowflake billing within the rubric tolerance. A seeded anomaly fires the correct alert. The agent answers golden questions with citations.

### M2 — Extraction Agent & Harvest (SQL Server first, then Oracle, Teradata)
- [ ] Read-only connectors, permission manifests, harvest → canonical model
- **Accept:** kill-test proves no write capability; harvest of a sample database populates objects, dependencies, usage

### M3 — Assessment Engine
- [ ] Disposition classifier (usage + lineage + AI) with confidence/rationale; complexity scoring; anti-pattern detection; drift-risk scan
- [ ] Assessment snapshot + report export
- **Accept:** re-running assessment on same snapshot + rubric version reproduces identical scores; low-confidence items appear in review queue

### M4 — Planning & Estimation
- [ ] Wave clustering from dependency graph; pattern recommender; estimation engine (p50/p80, confidence)
- **Accept:** estimates reference rubric version and are reproducible; wave plan respects gate rules stored as data

### M5 — Conversion Orchestrator
- [ ] SnowConvert AI CLI integration; EWI ingestion; AI remediation agent producing PRs with tests; review workflow
- **Accept:** no artifact promotable without review; every AI change has confidence, rationale, model and prompt version

### M6 — Validation Engine
- [ ] L0–L5 suite generator; normalisation rules as data; in-boundary execution; mismatch clustering agent; accepted-deviation workflow
- **Accept:** synthetic drift cases (TD-01, TD-02, OR-01, MS-01) are detected and correctly clustered to their known issue

### M7 — Foundation Accelerators
- [ ] Terraform landing-zone generator from YAML role/warehouse model; Well-Architected checker
- **Accept:** generated Terraform applies to a trial account; checker reports findings with remediation playbooks

### M8 — Portal & Sherpa
- [ ] Progress boards, evidence drill-through, review queues, Sherpa chat grounded in snapshot with citations; Review Board ADR flow
- **Accept:** every number on a board links to evidence IDs; Sherpa answers cite evidence and refuse when ungrounded

### M9 — ETL & Scheduler Converters
- [ ] SSIS and Informatica parsers → mapping graph → dbt generation; scheduler → task graph/Airflow
- **Accept:** sample packages produce dbt projects that compile and pass generated tests on synthetic data

### M10 — Agent Fleet v1
- [ ] Cost Sentinel, Warehouse Rightsizer, Pipeline Triage, Access Hygiene, DQ Incident, Release Change Watcher as Cortex Agents with tool scopes, eval suites and approval workflow
- **Accept:** L2 actions never execute without approval; L3 actions limited to the pre-approved catalogue with auto-rollback test

### M11 — AI-Ready Module
- [ ] EAIRN-style scoring on Snowflake; semantic view generator; Cortex Search/Agent templates with evaluation harness
- **Accept:** readiness score reproducible per snapshot; semantic views generated from KPI registry with one definition per KPI enforced

### M12 — Editions, MCP & Packaging
- [ ] MCP server exposing skills; Native App packaging; white-label theme tokens; board-pack export (PPTX/PDF from snapshot)
- **Accept:** de-branding lint passes (no raw brand strings/colours outside token files); exported deck and dashboard read from the same snapshot

---

# APPENDICES

## Appendix A — Known-Issues Register Entry (YAML)

```yaml
known_issue:
  id: OR-01
  source_dialect: oracle
  title: "Empty string treated as NULL in Oracle; distinct value in Snowflake"
  severity: S1
  symptoms:
    - "Row counts match but COUNT(col) and IS NULL filters differ"
    - "String concatenation results differ"
  detection:
    type: static_and_profile
    static_rule: "Predicates using IS NULL / IS NOT NULL / NVL / COALESCE on VARCHAR2 columns"
    profile_rule: "Null-count on Snowflake side lower than source for same column after load"
  fix_patterns:
    - id: FX-OR-01-A
      description: "Normalise at ingestion: NULLIF(TRIM(col), '') for VARCHAR columns in raw→silver"
      applies_when: "Programme policy = oracle_null_semantics"
    - id: FX-OR-01-B
      description: "Rewrite predicates: (col IS NULL OR col = '')"
      applies_when: "Raw layer must preserve exact source values"
  tests: [TC-OR-01-001, TC-OR-01-002]
  validation_normalisation: "treat '' and NULL as equal for L3 hashing when policy A applied"
  decision_required: true      # programme-level ADR
  last_verified: 2026-10-01
  verified_by: practice-lead-oracle
```

## Appendix B — Assessment Questionnaire (Supplements Machine Evidence)

**Business & constraints**
1. What are the hard deadlines (licence, hardware, data-centre exit) and their consequences?
2. Which processes are regulatory or financial-close critical? Blackout windows?
3. What is the appetite for modernisation vs speed (1–5)?

**Estate**
4. Which sources, versions and sizes are in scope? Which are OLTP vs analytical?
5. ETL tools, schedulers and BI tools in use; approximate job/report counts?
6. How long is query/usage history retained on each source?
7. Known undocumented integrations (DB links, file drops, linked servers)?

**Semantics & policy (decisions needed early)**
8. Target policy for case sensitivity, NULL vs empty string, timestamp types and time zones?
9. Which tables are Tier-1 for reconciliation?
10. Acceptable reconciliation tolerances per data domain?

**Security & governance**
11. Identity provider; MFA; network requirements (private connectivity)?
12. Classification scheme; PII/PHI/PCI locations; masking requirements?
13. Who owns data domains today? Is ownership documented?

**Operations & AI**
14. Who will run the platform after go-live? Appetite for managed service and autonomous agents (L0–L3)?
15. AI ambitions (Cortex Analyst, Search, Agents) and current blockers?
16. Approved LLM endpoints and data-handling restrictions?

Answers are cross-validated against harvested evidence; contradictions ("we have no unused objects" vs 48% unused) become findings.

## Appendix C — Readiness Gates (as data, abridged)

```yaml
gates:
  assess_exit:
    - { metric: objects_classified_pct, op: ">=", ref: rubric.gates.assess_classified_min }
    - { metric: tier1_identified, op: "==", value: true }
    - { metric: business_case_approved, op: "==", value: true }
  convert_exit:
    - { metric: open_p1_ewis, op: "==", value: 0 }
    - { metric: ai_changes_unreviewed, op: "==", value: 0 }
    - { metric: unit_test_pass_rate, op: ">=", ref: rubric.gates.unit_test_min }
  cutover_go:
    - { metric: tier1_l3_mismatches_unaccepted, op: "==", value: 0 }
    - { metric: consecutive_clean_parallel_cycles, op: ">=", ref: rubric.gates.parallel_cycles_min }
    - { metric: rollback_rehearsed, op: "==", value: true }
    - { metric: grants_mapped_pct, op: "==", value: 100 }
```

## Appendix D — Recommended First 90 Days (Founder Checklist)
1. **Legal and IP clearance first.** Review the employment contract's IP-assignment, non-compete, non-solicit and conflict clauses with counsel. Adopt a written **clean-room policy**: earlier accelerators are know-how only, with no code, documents, KPI lists or client artefacts carried over.
2. Choose a trademark-clear brand name with no Snowflake marks.
3. Register with the Snowflake Partner Network and complete SnowPro certifications.
4. Build the D0 Snapshot and Package D v1 checks (D1–D6) and the Package O Core KPI tier, clean-room.
5. Run free D0 Snapshots for 10 target accounts (utilities first) and convert 1–2 into paid Package D design partners.
6. Publish the open-source drift checker and one data-backed article.
7. Record effort and value (identified vs realised) from day one. This calibrates the estimation engine and becomes the proof behind the differentiators.

## Appendix E — Glossary
**ADR** architecture decision record · **CDC** change data capture · **DMF** data metric function · **EWI/FDM** SnowConvert conversion warnings/functional-difference messages · **L0–L3** agent autonomy levels · **L0–L5 (validation)** validation depth levels · **Tier-1** critical/regulatory data assets · **Pattern Library** codified mappings, issues, fixes and tests · **Sherpa** ALTITUDE's AI delivery partner · **Native edition** deployment inside the client's Snowflake account.

## Appendix F — v1.1 Consulting Review of v1.0: Findings & Changes

| # | Finding on v1.0 | Severity | Change made in v1.1 |
|---|---|---|---|
| 1 | The value proposition led with "AI-accelerated migration", which is now table stakes (SnowConvert AI, phData Forge, Hakkoda AI migrations) | High | Repositioned as "evidence-first"; honest table-stakes test and eight differentiators (Section 4) |
| 2 | The entry motion depended on multi-year migrations that need references a startup does not have | High | Beachhead moved to Diagnose → Observe on existing Snowflake estates (Packages D and O); build plan resequenced (Section 36) |
| 3 | Breadth exceeded startup capacity: 13 sources, 11 streams, 16 agents, 7 revenue lines | High | Focus sequence set: SQL Server/Oracle migrations in phase 2, Teradata/Netezza factories in phase 3; offer ladder (Section 5.3) |
| 4 | The founder's strongest proven assets (BI rationalisation, KPI lineage, observability framework) were under-used | High | Promoted to differentiators 2 and 3 and built into Packages D and O, with a clean-room requirement |
| 5 | The IP provenance risk was generic | High | Specific risk row (Section 37) and clean-room policy (Appendix D) |
| 6 | Speed claims ("30–50% faster") were unsubstantiated | Medium | Restated as targets pending calibration (Sections 3.2, 32) |
| 7 | The "Health Check" overlapped with Snowflake's free WAF assessment | Medium | Package D aligned to the 5 WAF pillars plus 5 extension domains; the free WAF assessment is used as an input (Section 6.2) |
| 8 | There was no pricing, offer ladder or unit economics | Medium | Indicative tiers, conversion assumptions and margin guardrails (Sections 5.3–5.4, 6.7, 7.7) |
| 9 | There were no outcome-based commercials | Medium | Fee credit, value floor, re-baseline; flat spend-band pricing for Package O |
| 10 | Least-privilege access was not specified | Medium | `SNOWFLAKE` database roles, no ACCOUNTADMIN, credit-capped diagnostics warehouse (Section 6.10) |
| 11 | No "why choose us" in buyer language, and no statement of when not to choose ALTITUDE | Medium | Sections 4.4–4.5 |
| 12 | Tension with Snowflake account teams' incentives around cost reduction was not addressed | Low | "Efficiency funds new workloads" framing (Sections 35, 37) |

**Open decisions for the founder**
1. Which vertical the first three design partners come from (recommended: utilities).
2. Whether to bootstrap on services cash flow or raise an early seed round.
3. The Package O code licensing model: client-owned deployment or a licensed Native App (Section 7.9).
4. Appetite for the value-floor guarantee, and the qualification threshold.
5. Delivery footprint: a US-only senior team, or blended onshore/offshore delivery.

---
*End of specification v1.1. Suggested next deliverables: Package D check catalogue YAML (v0, 40 checks), Package O Core KPI definitions, a two-page Package D + O offer sheet, and a design-partner pitch deck.*
