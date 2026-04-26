# Global Mother Agent Architecture

## Scope

Mother Agent is the universal orchestrator for any task that requires an agentic approach. It is not tied to any specific task type, channel, or workflow. Wherever agents are involved in getting work done, the Mother Agent governs how that work is handled.

## Universal flow

1. Request enters from any source
2. Mother Agent classifies task
3. Circuit breaker check — halt if error rate > 5% for this label in 1h window
4. Load shed check — queue if 4 children already running
5. Mother Agent decides:
   - direct execution, or
   - worker delegation (up to 3 child agents with failover)
6. Worker output returns to Mother Agent
7. Mother Agent validates output quality
8. If all child agents fail, Mother Agent self-executes (not delegated)
9. If Mother self-execution also fails → honest escalation to the requester or operator
10. Only then is the task considered complete

## Principles

- Mother Agent applies universally — any task involving agents falls under its governance
- one supervising owner per task
- worker outputs are provisional until validated
- failure handling is internal whenever possible
- channels do not own orchestration logic
- Mother Agent is the final authority on task completion
- Circuit breaker prevents cascade failures when error rate exceeds 5% per label
- Load shedding ensures no more than 4 children run concurrently — excess is queued
