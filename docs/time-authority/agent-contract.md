---
id: roko-time-authority.agent-contract
title: Agent execution contract
summary: Deterministic traversal and bounded execution rules for any operations agent.
audience: [agent, operator]
tasks: [route, plan, execute, report]
status: stable
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Delegating time or ROKO node deployment to an agent.
previous: troubleshooting.md
next: README.md
---

# Agent execution contract

Start at this docset's [`README.md`](README.md). Read `docset.yaml`, then follow
the route matching the operator's role. Read every selected page completely;
do not crawl unrelated repository content or improvise policy from filenames.

## Required protocol

1. Identify hobbyist or professional scope, geography, node role, runtime,
   whether NTP will be served, and whether Timebeat is selected.
2. Route through `concepts.md` and `choose-sources.md`, then the applicable role
   pages and `verification.md`.
3. Collect all parameters before changes. Request paths to protected files,
   never their contents.
4. Inspect the selected manifest and scripts.
5. Run the guided installer with `--dry-run`.
6. Show the resolved plan and wait for explicit approval.
7. Execute only the approved plan.
8. Report success only after the complete acceptance gate passes.

## Hard boundaries

Do not expose private timing topology, reveal secrets, open RPC, broaden
firewall access, delete chain data, lower the two-source requirement, enroll or
activate a validator, or equate an active service with readiness. Stop for
approval before actions outside the printed plan.

## Completion report

Return role, region, selected source hostnames and observed strata, selectable
source count, leap state, clock owner, installed versions, ROKO synchronization
and finality evidence, temporal convergence where applicable, report path,
failed/skipped gates, and next reviewed action. Exclude private values.

---

Pagenbar: [← Troubleshooting](troubleshooting.md) · [Index](README.md) · [Loop to orientation →](README.md)
