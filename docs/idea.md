# The idea

A material holds several times at once. A model that just names it flattens them.
This loop keeps the ambiguity open: ask the model what happened to the thing, then undo that.

## Walk backwards

```
forward   host body --> rust stain --> crust        (what happened)
photo                                  [crust]      (what we have)
loop      [crust] --> [rust stain] --> [host body]  (undo, step by step)
```

## Layers peeled one at a time

```
step 0        step 1          step 2         step 3
~~~~~~ crust  ------ stain    ====== body    ?
------ stain  ====== body
====== body
```

## One step

```
image
  | what is it?         3 guesses (any domain)
  v
"rusted cast iron"      top guess = the material
  | what happened to it?
  v
DEPOSIT                 one operation from the lexicon
  | undo it
  v
Klein: show it BEFORE   -> new image -> next step
```

## What moves, what stays

```
stays     shape: ridges, cavities, framing       (inherits the past)
undone    surface: crust, stain, colour          (the operation)
shifts    what the model thinks it is            (the finding)
```

## Recognition drifts across domains

```
original   ceramic / metal, grey crust
step 3     geode-like rock
step 5     corroded metal
step 6     molded egg carton
step 8     black flint
step 10    carved plaster sculpture
```

Each step reads the image fresh, with no history. The reading is an event that redirects the next step.

## How it is meant to read

```
guesses before         guesses after
1. rusted metal        1. weathered stone
2. lichen crust        2. rusted metal
3. efflorescence       3. plaster
        \_____ ambiguity moves, it does not collapse _____/
```
