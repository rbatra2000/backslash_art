# How the system works

The loop walks a material sample **backwards in time**: read the image, infer what happened to the material, undo it, repeat.

## Who does what

| Actor | Model | Sees | Produces |
|---|---|---|---|
| **Planner** (reader) | Claude vision (`claude-sonnet-5-5`) | the current image, the lexicon, what was already undone | 3 ranked identities, formation hypothesis, one operation, keep/undo lists |
| **Image editor** | FLUX 3 Klein (BFL API) | the current image + the assembled prompt | one image: the sample *before* the operation |
| **Blind judge** | Claude vision, fresh call | before + after images, operation definition only | undone (yes/no), changed, kept, lost |
| **Blind re-reader** | Claude vision, fresh call | the result image only | 3 ranked identities of the result |
| **Code** (no model) | Python | files | builds the prompt from a template, pixel-diff flag, writes `events.jsonl` |

**4 model roles, 0 persistent agents.** Every role is a stateless API call (3 Claude + 1 Klein per step, so about 30 + 10 for a 10-step run). Nothing remembers anything between calls; the only state carried forward is the image and the list of operations already undone.

**The identities come from Claude.** The Planner ranks them for the step's input; the Blind re-reader ranks them again for the result. There is no classifier or embedding model. The labels, their order and the evidence are the model's own judgment; their probabilities are kept in `record.json` but are not calibrated and are not shown in the UI.

## One step

```mermaid
flowchart TD
    IMG["current image<br/>(step 1: your original)"] --> PLAN

    subgraph PLAN["1 - PLAN (Claude, sees image + lexicon + history)"]
        direction TB
        R["3 ranked identities<br/>with evidence"] --> F["formation hypothesis<br/>for the TOP identity"]
        F --> OP["pick 1 operation<br/>from lexicon.yaml"]
        OP --> KA["keep list / undo list"]
    end

    PLAN --> PR["2 - PROMPT<br/>(template, no model)<br/>remove undo list, show clean<br/>material underneath, keep keep list"]
    PR --> GEN["3 - GENERATE one image<br/>(FLUX 3 Klein)"]
    GEN --> OUT["result image"]

    subgraph REFLECT["4 - REFLECT (two fresh, stateless Claude calls)"]
        direction LR
        J["blind judge<br/>before + after only<br/>undone yes or no<br/>changed / kept / lost"]
        BR["blind re-read<br/>result only<br/>3 ranked identities"]
    end

    IMG --> J
    OUT --> J
    OUT --> BR
    OUT --> NEXT["5 - becomes the next step's image"]
    BR -. "shown as next step's 'before' reading" .-> NEXT
    NEXT -. "repeat (10 steps)" .-> IMG
```

## Why a blind re-reader

The project measures how the model's *recognition* shifts as the sample is unmade. The judge can't show that: it compares two images for one operation and returns no identities. The re-reader gives the "after" reading, used two ways:

- the **reading shift** shown under "+ why" (what the result now reads as);
- the next step's **"before" reading**, so every displayed reading is context-free.

The Planner reads the same image again at the next step, but with history attached, which nudges its identities. So its read picks the operation and the blind read is what's displayed. Dropping the re-reader would save one call per step but mix history into the readings you compare.

## How the operation is picked

```mermaid
flowchart LR
    A["top-ranked identity<br/>e.g. rusted metal casting<br/>with grey mineral crust"] --> B["most likely process<br/>to have happened to<br/>that kind of material<br/>e.g. crust built up"]
    B --> C["lexicon entry that names it<br/>DEPOSIT"]
    C --> D["UNDO it:<br/>show the sample before<br/>the crust accumulated"]
```

- The choice is restricted to the 18 operations in `lexicon.yaml` (three groups: formation, unmaking, reorganization).
- It picks the process that *happened*, then the loop undoes it. A crust that built up is DEPOSIT; the step removes the crust.
- Repeats are allowed. Earlier undone steps are shown to the planner only so it doesn't name products that are already gone.
- All model text is kept terse: caps on words are in the system prompts (labels 8 words, reasoning 10-12, judge lists 2 short phrases).

## What stays blind

```mermaid
flowchart LR
    subgraph sees["Planner sees"]
        s1["current image"]
        s2["lexicon"]
        s3["operations already undone"]
    end
    subgraph blind["Judge and re-reader see ONLY"]
        b1["the two images<br/>(or just the result)"]
        b2["operation definition"]
    end
    subgraph never["Never shown to judges"]
        n1["the prompt"]
        n2["earlier steps"]
        n3["the planner's reasoning"]
    end
```

Every judgement starts from the same fixed system prompt, so no call inherits another's framing.

## What gets recorded

```
runs/<id>/
  run.json            config, lexicon, git commit, model names
  events.jsonl        every stage, followed live by the UI
  step_01/
    input.png         what the planner saw
    result.png        what Klein generated
    record.json       plan, prompt, seed, judge reflection, blind re-read, flags
```

## Known limits

- Nothing checks that the chosen operation is physically coherent beyond Claude's reasoning and the lexicon wording.
- Klein has no strength setting, so how much it undoes depends on prompt wording alone.
- The pixel diff is the only measured number; it only raises an "image barely changed" flag.
