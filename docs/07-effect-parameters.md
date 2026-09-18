# 07 — Characterising the effect parameters

Status: **open**. This document is a protocol to run, not a result.

## The question

Every animated mode carries two registers. The vendor application calls them *response*
and *speed*, and `docs/05-led-protocol.md` repeats those names — but the names were taken
from the app's method names, never verified against behaviour.

For Rainbow they are:

| register | vendor name | factory default |
|---|---|---|
| `0x18` | response | 2 |
| `0x19` | speed | 5 |

Observation from use: **raising `0x19` makes the rainbow gradient narrower**, not faster.
If that holds, `0x19` is a spatial parameter and the driver is wrong to drive it from
OpenRGB's speed slider.

## Why earlier attempts failed

Earlier rounds asked "did the speed change?" and got contradictory answers across
sessions — first yes, then no perceptible difference, then yes again. The question is the
problem, not the observer: **a shorter gradient moves more colours past a fixed point in
the same time**, so a purely spatial change reads as faster. Subjective judgement cannot
separate the two.

## Method

Record two independent numbers for every combination:

- **BANDS** — how many distinct colour bands you can count across the 14 LEDs.
  A spatial parameter changes this. A temporal one does not.
- **CYCLE** — seconds for the pattern to repeat. Watch a single LED and time the gap
  between two moments it shows the same colour. A temporal parameter changes this. A
  spatial one does not.

Counting bands is easier with the strip paused mentally rather than tracked: look at the
whole strip at once and count how many times the colour sequence restarts.

Timing a cycle is easier at low rates. If a cycle is too fast to time, write "too fast"
rather than guessing.

## Running a step

```sh
tools/param-probe.sh <response> <spread>
```

It sets Rainbow, full strip length and default brightness, then the two registers under
test — one register per transaction, as the hardware requires.

## Schedule

Run the steps in order. Steps 1 to 4 hold `0x19` fixed and vary `0x18`; steps 5 to 8 do
the reverse. Step 1 is the baseline and is worth repeating at the end to check the
readings are reproducible.

| # | command | 0x18 | 0x19 | BANDS | CYCLE (s) |
|---|---|---|---|---|---|
| 1 | `tools/param-probe.sh 2 5` | 2 | 5 | | |
| 2 | `tools/param-probe.sh 1 5` | 1 | 5 | | |
| 3 | `tools/param-probe.sh 4 5` | 4 | 5 | | |
| 4 | `tools/param-probe.sh 10 5` | 10 | 5 | | |
| 5 | `tools/param-probe.sh 2 2` | 2 | 2 | | |
| 6 | `tools/param-probe.sh 2 8` | 2 | 8 | | |
| 7 | `tools/param-probe.sh 2 20` | 2 | 20 | | |
| 8 | `tools/param-probe.sh 2 40` | 2 | 40 | | |
| 9 | `tools/param-probe.sh 2 5` | 2 | 5 | | *(repeat of 1)* |

Extra checks, only if the table above leaves it ambiguous:

| # | command | what it tests |
|---|---|---|
| 10 | `tools/param-probe.sh 0 5` | does `0x18 = 0` freeze the effect, as suspected? |
| 11 | `tools/param-probe.sh 10 40` | do both at maximum interact, or stay independent? |

## Reading the table

| BANDS changes with | CYCLE changes with | conclusion |
|---|---|---|
| `0x19` only | `0x18` only | clean split: `0x18` is rate, `0x19` is gradient width |
| `0x19` only | neither | `0x19` is width; rate is fixed or lives elsewhere |
| both | both | the two are coupled; treat as one control |
| neither | `0x19` only | the original reading was wrong and `0x19` really is speed |

## If the split is confirmed

Three things change:

1. `docs/05-led-protocol.md` renames `0x19` from "speed" to whatever it turns out to be,
   and notes the vendor's name is misleading.
2. The OpenRGB driver maps its speed slider to `0x18` instead of `0x19`, and leaves `0x19`
   at the vendor default — OpenRGB has no generic control for gradient width.
3. `tools/lumi-led.py` gains a separate flag for the spatial parameter, since the CLI is
   not constrained by OpenRGB's mode structure.

## Then the other modes

The same pair exists for Serial (`0x16`/`0x17`) and Runway (`0x11`/`0x12`, plus `0x29`).
If Rainbow splits cleanly, the same protocol should be run for those before assuming the
result carries over. Block Stacking (`0x20`) and Breathing (`0xC8`) have a single parameter
each, so there is nothing to separate.

## Results

Fill in as the steps are run. Record the date and anything that made a reading uncertain.
