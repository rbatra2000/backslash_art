# Overview

Walk a material sample **backwards in time**: read it, infer what happened to it, undo that, repeat.
A model that just names a material flattens its histories; asking what happened to it keeps them open.

![original, then steps 1, 3, 4, 6, 10](example_chain.jpg)

## Layers, peeled one at a time

```
photo         after step 1    after step 2    after step 3
~~~~ crust    ---- stain      ==== body       ?
---- stain    ==== body
==== body
```

## One step

```
image
  | what is it?          planner: one guess (any domain)
  v
"rusted cast iron"       the guess = the material
  | what happened to it? planner: one operation from the lexicon
  v
DEPOSIT
  | undo it
  v
Klein: show it BEFORE    -> new image -> next step
```

```mermaid
sequenceDiagram
    participant C as Code
    participant P as Planner (Claude)
    participant K as Klein
    C->>P: image + lexicon
    P-->>C: identity, process, operation, keep/undo
    C->>K: image + prompt from template
    K-->>C: result image
```

Every planner call is stateless: it sees only the current image and the lexicon. The image is all that carries over.

## What moves, what stays

```
stays    shape: ridges, cavities, framing      (inherits the past)
undone   surface: crust, stain, colour         (the operation)
shifts   what the model thinks it is           (the finding)
```

## Recognition drifts across domains

```
original  rusted metal casting, gray crust
step 3    gray-coated porous foam or ceramic
step 4    cream porous stone or plaster
step 6    skull-like plaster or bone cast
final     plaster-like sculpted porous solid
```

## Lexicon (`lexicon.yaml`)

```mermaid
flowchart LR
    L[operations] --> F[formation<br/>DEPOSIT, PRECIPITATE, CRYSTALLIZE, SINTER, CEMENT, INFILTRATE]
    L --> U[unmaking<br/>DISSOLVE, ERODE, FRACTURE, DELAMINATE, BURN OUT, LEACH]
    L --> O[reorganization<br/>DEVITRIFY, PHASE SEPARATE, COARSEN, FOLD, CREEP, MIGRATE]
```
