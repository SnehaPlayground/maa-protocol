# WhatsApp Framework — Primeidea Build

Status: NOT BUILT — design only. WhatsApp business assistant is not yet implemented.
This document describes the target state but is not active production code.
Do not reference this as live operational capability.

## Objective
Build a bulletproof, reusable WhatsApp business assistant framework for Primeidea that can later be adapted for other businesses.

## Current source assets reused from legacy helper
- phone normalization concept
- employee/external classification concept
- state tracking concept
- existing WhatsApp group metadata file

## New target capabilities
- public DM intake
- silent group monitoring unless tagged
- in-scope finance reply flow
- out-of-scope private escalation behavior
- Telegram owner control
- structured lead logging
- private error alerting
- reusable business knowledge pack

## Non-goals for first build
- unsolicited outbound campaigns
- autonomous posting without owner command
- unsupported claims beyond approved knowledge pack

## Next implementation steps
1. build Primeidea knowledge pack
2. map owner commands
3. define logging schema
4. migrate useful legacy pieces
5. archive legacy helper
6. validate live routing before activation
