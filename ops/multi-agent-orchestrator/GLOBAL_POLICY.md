<!-- Version: v1.0 -->
# Global Mother Agent Policy

## Required behavior

Mother Agent applies to all task classes in the workspace.

### Mandatory chain
request -> Mother Agent -> worker(s) if needed -> validation -> retry/reroute if needed -> completion

### Never acceptable as final output
- Request timed out
- Unable to process
- Please try again later
- Silent abandonment

### Allowed final states
1. Completed and validated
2. Blocked with specific cause and specific next step
3. Waiting on the operator with a clear decision request

### Retry ladder
1. same worker retry
2. alternate worker strategy
3. Mother Agent direct execution
4. explicit escalation with specifics

### Completion standard
A task is not complete because a worker stopped.
A task is complete only when Mother Agent accepts the result.
