# Architecture

Walk a material sample **backwards in time**: read it, infer what happened to it, undo that, repeat.

![example chain](example_chain.jpg)

## The loop

```mermaid
flowchart LR
    A[image] --> B[plan]
    B --> C[prompt]
    C --> D[Klein]
    D --> A
```

## One step

```mermaid
sequenceDiagram
    participant C as Code
    participant P as Planner (Claude)
    participant K as Klein
    C->>P: image + lexicon
    P-->>C: 3 identities, process, operation, keep/undo
    C->>K: image + prompt from template
    K-->>C: result image
```

2 model roles, 0 persistent agents: every call is stateless. The planner sees only the current image and the lexicon, so every reading starts from the same point. One last read after the final step.

## Picking the operation

```mermaid
flowchart LR
    A[top identity] --> B[most likely process<br/>for that material] --> C[lexicon operation] --> D[undo it]
```

## Operation groups

```mermaid
flowchart LR
    L[lexicon] --> F[formation<br/>DEPOSIT, PRECIPITATE, CRYSTALLIZE, SINTER, CEMENT, INFILTRATE]
    L --> U[unmaking<br/>DISSOLVE, ERODE, FRACTURE, DELAMINATE, BURN OUT, LEACH]
    L --> O[reorganization<br/>DEVITRIFY, PHASE SEPARATE, COARSEN, FOLD, CREEP, MIGRATE]
```

## Run output

```mermaid
flowchart LR
    run[runs/timestamp] --> a[run.json] & b[events.jsonl] & f[final.json] & s[step_NN]
    s --> s1[input.png] & s2[result.png] & s3[record.json]
```
