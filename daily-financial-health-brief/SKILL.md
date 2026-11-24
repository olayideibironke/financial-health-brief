---
name: daily-financial-health-brief
description: Fetch three live Google Sheets, normalize and validate their financial records, and produce deterministic CSVs and a traceable draft brief for human review.
---

# Daily Financial Health Brief

Run from the repository root with:

    python daily-financial-health-brief/scripts/run.py --help

The command fetches each supplied Google Sheet through its published CSV view, identifies source roles by required schema, validates complete retrieved populations, and writes the normalized CSVs and a traceable report. It uses read-only HTTP requests and Decimal arithmetic. Read references/contract.md for the contract and unresolved-policy configuration. Fetch or validation failure clears required deliverables before exiting nonzero.
