# Codyssey

> **An autonomous journey from bug report to verified fix.**

Codyssey is a repository-level **automated program repair agent** designed to take a real software bug, locate its probable source, generate candidate fixes, execute tests in an isolated environment, learn from failures, and iteratively search for a verified repair.

Rather than treating an LLM as the entire solution, Codyssey explores a **cost-aware hybrid approach** that combines traditional program analysis, repository intelligence, automated testing, and selective LLM reasoning.

---

## The Problem

Fixing a repository-level bug involves much more than generating a few lines of code.

A developer typically has to:

1. Understand the reported issue.
2. Navigate a potentially large repository.
3. Identify relevant files and functions.
4. Reproduce the failure.
5. Determine the probable fault location.
6. Form a repair hypothesis.
7. Modify the code.
8. Run tests.
9. Analyze failures.
10. Repeat until the bug is actually fixed.

Modern LLMs can assist with many of these steps, but repeatedly sending large amounts of repository context to an LLM can be expensive and inefficient.

Codyssey asks a different question:

> **Can an autonomous repair agent solve repository-level bugs while minimizing expensive LLM interactions?**

---

## What is Codyssey?

Codyssey is an **agentic automated program repair system**.

Given a repository and a bug report, the system attempts to autonomously move through the repair process:

```text
GitHub Issue + Repository
            │
            ▼
      Reproduce Failure
            │
            ▼
      Repository Analysis
            │
            ▼
       Fault Localization
            │
            ▼
    Retrieve Relevant Code
            │
            ▼
      Generate Candidate Fix
            │
            ▼
       Apply Patch
            │
            ▼
    Run Tests in Sandbox
            │
       ┌────┴────┐
       │         │
      PASS      FAIL
       │         │
       ▼         ▼
   Verified    Analyze
     Fix       Failure
                 │
                 ▼
            Revise Repair
                 │
                 └──────────↺
```

The process continues until Codyssey verifies a repair or reaches its configured repair budget.

---

## Why Not Just Ask an LLM?

An LLM can generate code, but an LLM by itself is not a complete repair system.

Codyssey surrounds the reasoning component with tools capable of interacting with the actual software environment.

```text
               ┌─────────────────┐
               │     Codyssey    │
               │                 │
               │  Repair Engine  │
               └────────┬────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
   Repository       Program         Test/Sandbox
     Search         Analysis          Execution
        │               │               │
        └───────────────┼───────────────┘
                        ▼
                  Repair Decision
                        │
                        ▼
                   Apply Patch
                        │
                        ▼
                  Observe Result
                        │
                        └──────↺
```

The goal is not to make the LLM perform every step.

Instead, Codyssey attempts to use deterministic and inexpensive techniques wherever possible and reserve expensive model reasoning for situations where it provides meaningful value.

---

## Hybrid Repair Strategy

Codyssey can combine two repair mechanisms.

### 1. Traditional Automated Program Repair

For common classes of bugs, Codyssey can generate candidate patches using predefined repair operators.

Examples include:

```text
>   → >=
<   → <=
==  → !=
&&  → ||
```

Other repair operators may include:

- null guards
- boundary-condition modifications
- boolean-condition mutations
- constant replacement
- default return values
- expression replacement
- reuse of existing expressions
- conditional insertion/removal

Candidate patches are automatically validated against the project's test suite.

### 2. Selective LLM-Assisted Repair

When deterministic repair strategies cannot produce a valid fix, Codyssey can selectively invoke an LLM.

Instead of sending the entire repository, Codyssey attempts to retrieve only the most relevant context:

```text
Bug Report
    +
Suspicious Functions
    +
Relevant Source Code
    +
Failing Tests
    +
Stack Trace
    +
Relevant Git History
         │
         ▼
        LLM
         │
         ▼
  Candidate Repair
```

This reduces unnecessary token consumption while still allowing complex semantic repairs.

---

## Cost-Aware Agent Design

LLM calls are treated as a limited resource.

A repair session can operate under constraints such as:

```text
Maximum LLM calls
Maximum input/output tokens
Maximum repair attempts
Maximum sandbox execution time
Maximum total repair time
```

Before requesting LLM reasoning, the agent can determine whether a cheaper action may provide additional information.

For example:

```text
Test Failed
    │
    ▼
Can additional static analysis,
coverage or repository search help?
        │
   ┌────┴────┐
  YES       NO
   │         │
   ▼         ▼
Cheap      Invoke
Analysis     LLM
   │         │
   └────┬────┘
        ▼
   Next Action
```

---

## Core Components

### Repository Analyzer

Explores the repository and extracts information such as:

- project structure
- source files
- functions and classes
- dependencies
- related tests
- call relationships
- Git history

### Fault Localizer

Identifies code that is likely responsible for a failing test.

Potential techniques include:

- stack-trace analysis
- test coverage
- suspiciousness scoring
- Ochiai fault localization
- dependency/call-graph analysis

### Repair Engine

Generates candidate patches using deterministic repair operators or LLM-assisted generation.

### Sandbox Executor

Applies candidate patches in an isolated environment and executes the project's tests without modifying the original repository.

### Feedback Loop

Test results are fed back into the repair process.

```text
Generate
   ↓
Patch
   ↓
Execute
   ↓
Observe
   ↓
Evaluate
   ↓
Revise
   ↺
```

### Cost Controller

Tracks and limits expensive operations including:

- LLM calls
- input tokens
- output tokens
- estimated API cost
- repair attempts
- execution time

---

## Research Goals

Codyssey investigates whether repository-level automated repair can become more efficient by combining traditional software-engineering techniques with selective LLM reasoning.

Some questions we aim to explore include:

**RQ1.** How effectively can Codyssey repair real repository-level software bugs?

**RQ2.** Can program analysis and fault localization reduce the amount of repository context sent to an LLM?

**RQ3.** Can traditional repair operators solve simpler bugs without requiring an LLM?

**RQ4.** How does a hybrid repair strategy compare with a pure LLM-based repair agent?

**RQ5.** What trade-off exists between repair success rate and LLM inference cost?

---

## Evaluation

Codyssey can be evaluated using real software bugs and GitHub issues with known human-written fixes.

For each bug, the human patch can be hidden from the system.

Codyssey receives:

```text
Repository state before fix
            +
        Bug report
            +
        Test suite
```

It must independently generate and verify a repair.

The resulting patch can then be compared against the actual developer fix.

### Metrics

| Metric | Description |
|---|---|
| Repair Success Rate | Percentage of bugs successfully repaired |
| Test Pass Rate | Tests passing after generated repair |
| LLM Calls | Number of model invocations |
| Input Tokens | Tokens sent to the model |
| Output Tokens | Tokens generated by the model |
| Estimated Cost | Approximate model cost per repair |
| Repair Attempts | Number of candidate patches attempted |
| Time to Repair | End-to-end repair duration |
| Patch Size | Size of the generated modification |

A particularly useful metric is:

```text
Cost per Successful Repair
```

which measures whether improvements in repair capability justify additional inference cost.

---

## Experimental Comparison

Codyssey can compare three approaches:

```text
Traditional APR
      vs.
Pure LLM Repair Agent
      vs.
Hybrid Codyssey Agent
```

This allows us to study both repair capability and computational cost.

| Approach | Program Analysis | LLM | Test Feedback | Expected Cost |
|---|:---:|:---:|:---:|:---:|
| Traditional APR | ✓ | ✗ | ✓ | Low |
| Pure LLM Agent | Limited | ✓ | ✓ | High |
| Codyssey Hybrid | ✓ | Selective | ✓ | Controlled |

---

## Example

Consider a failing function:

```javascript
function canVote(age) {
    return age > 18;
}
```

with the failing test:

```javascript
expect(canVote(18)).toBe(true);
```

Fault localization identifies the condition as suspicious.

Codyssey's mutation engine generates:

```javascript
function canVote(age) {
    return age >= 18;
}
```

The sandbox executes the test suite.

```text
Before Patch

47 passed
1 failed

        ↓

Candidate Patch

age > 18
    ↓
age >= 18

        ↓

Run Tests

48 passed
0 failed

        ↓

VERIFIED REPAIR ✓
```

No LLM call was required.

More complex bugs can escalate to LLM-assisted repair.

---

## Proposed Tech Stack

**Core**

- Python
- Git / GitHub
- Docker
- pytest / repository-specific test runners

**Program Analysis**

- AST analysis
- coverage analysis
- stack-trace parsing
- Git history analysis
- fault-localization algorithms

**Agent**

- Python-based orchestration
- state machine / repair loop
- configurable repair budget
- tool execution layer

**Optional LLM Layer**

- configurable LLM API
- repository-context retrieval
- structured patch generation
- token and cost tracking

---

## Project Roadmap

**Phase 1 — Repair Infrastructure**

Repository ingestion → test execution → sandboxing → patch application.

**Phase 2 — Fault Localization**

Coverage collection → suspiciousness ranking → relevant-code retrieval.

**Phase 3 — Traditional APR**

Repair operators → candidate generation → automated validation.

**Phase 4 — Agentic Repair Loop**

Observe → select action → patch → execute → evaluate → retry.

**Phase 5 — LLM Integration**

Selective LLM escalation → context minimization → token/cost tracking.

**Phase 6 — Evaluation**

Real GitHub issues → baseline comparison → repair-rate analysis → cost analysis.

---

## What Makes Codyssey Different?

Codyssey is not intended to be another general-purpose coding assistant.

Its focus is the complete **repository-level repair lifecycle**:

> **Issue → Localization → Repair → Execution → Feedback → Verified Fix**

The system treats test execution as evidence, repair as an iterative search problem, and LLM inference as a powerful but expensive resource that should be used selectively.

---

## Status

🚧 **Research Prototype — Under Development**

Current focus:

```text
Repository Analysis
        ↓
Fault Localization
        ↓
Automated Repair
        ↓
Sandbox Verification
        ↓
Cost-Aware LLM Escalation
```

---

## Codyssey

**Code + Odyssey**

A journey through a codebase in search of the bug — and a verified way home.
