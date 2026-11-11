# Architecture

Walk a material sample **backwards in time**: read it, infer what happened to it, undo that, repeat.

![example chain: original, then three steps back](example_chain.jpg)

## The loop

```mermaid
flowchart LR
    A[image] --> B[plan]
    B --> C[prompt]
    C --> D[Klein]
    D --> E[result]
    E --> F[reflect]
    F --> A
```

## One step

```mermaid
sequenceDiagram
    participant C as Code
    participant P as Planner (Claude)
    participant K as Klein
    participant J as Judge (Claude)
    participant R as Re-reader (Claude)
    C->>P: image + lexicon
    P-->>C: 3 identities, process, operation, keep/undo
    C->>K: image + prompt from template
    K-->>C: result image
    par blind reflection
        C->>J: before + after
        J-->>C: undone yes/no, changed, kept, lost
    and
        C->>R: result only
        R-->>C: 3 identities
    end
```

4 model roles, 0 persistent agents: every call is stateless.

## Picking the operation

```mermaid
flowchart LR
    A[top identity] --> B[most likely process<br/>for that material] --> C[lexicon operation] --> D[undo it]
```

## What each call sees

```mermaid
flowchart TB
    subgraph Planner
        p1[image] ~~~ p2[lexicon] ~~~ p3[operations already undone]
    end
    subgraph Judge
        j1[before + after] ~~~ j2[operation definition]
    end
    subgraph Re-reader
        r1[result image only]
    end
```

## Operation groups (`lexicon.yaml`)

```mermaid
flowchart LR
    L[lexicon] --> F[formation<br/>DEPOSIT, PRECIPITATE, CRYSTALLIZE, SINTER, CEMENT, INFILTRATE]
    L --> U[unmaking<br/>DISSOLVE, ERODE, FRACTURE, DELAMINATE, BURN OUT, LEACH]
    L --> O[reorganization<br/>DEVITRIFY, PHASE SEPARATE, COARSEN, FOLD, CREEP, MIGRATE]
```

## Run output

```mermaid
flowchart LR
    run[runs/id] --> a[run.json] & b[events.jsonl] & s[step_NN]
    s --> s1[input.png] & s2[result.png] & s3[record.json]
```
