# 05 — The LED protocol (complete)

Extracted from the IL of `Onix.Controller.LightingController` in `LUMI.exe` v1.0.0.0, with
`tools/dotnet-il.py`. This is not guesswork: these are the bytes the official application
writes.

## Shape of a transaction

```
write N bytes to 0x28   →   read 1 byte
```

The P/Invoke signature, deduced from the IL stack:

```csharp
WriteReadAsync(byte[] writeBuf, int writeLen, byte[] readBuf, int readLen,
               IoCompleteCallback callback)
```

Every caller passes `readBuf = new byte[1]`. The application discards the byte. Measured on
hardware: it is an **echo of the last value written**, not a status code.

**The payload is a sequence of `(register, value)` pairs.** Several pairs can go in one
write — but **never together with a mode change**: batching `0x10` with colour and
brightness turns the lighting off, even though the command is accepted. Confirmed on
hardware, see `docs/06-hardware-validation.md`. The init sequence batches three pairs, and
there is no mode change in it.

No MCTP here. The MCTP framing in `docs/02-amc-protocol.md` is the *alert* channel the
kernel uses at the same address; the LED uses plain register writes.

## Register map

| reg | function | values |
|---:|---|---|
| `0x0F` | bypass | 0 = off, 1 = on |
| `0x10` | **mode** | see table below |
| `0x11` | Runway: **response** | default 10 — required, see below |
| `0x12` | Runway: interval | default 1 |
| `0x13` | OneColor: **response** | default 10 — required |
| `0x14` | direction | argument of `LedDirection` |
| `0x16` | Serial: **response** | default 2 — required |
| `0x17` | Serial: speed | default 16 |
| `0x18` | Rainbow: **response** | default 2 — required |
| `0x19` | Rainbow: speed | default 5 |
| `0x1A` | Custom: **R** | 0–255 |
| `0x1B` | Custom: **G** | 0–255 |
| `0x1C` | Custom: **B** | 0–255 |
| `0x20` | BlockStacking: speed | default 10 |
| `0x27` | **strip length** | `0x0E` = 14 LEDs |
| `0x29` | Runway: chaser | default 1 |
| `0x3E` | **brightness** | default `0x88` (136) |
| `0xC8` | Breathing: tempo | default 6 |
| `0xC9` | Breathing: **R** | 0–255 |
| `0xCA` | Breathing: **G** | 0–255 |
| `0xCB` | Breathing: **B** | 0–255 |

## Modes (register `0x10`)

| value | method in the app | effect |
|---:|---|---|
| `0x00` | `SetLedRainbowMode` | Rainbow |
| `0x01` | `SetLedCustomMode` | Custom — fixed colour via `0x1A`–`0x1C` |
| `0x02` | `SetLedBreathingMode` | Breathing — colour via `0xC9`–`0xCB` |
| `0x03` | `SetLedSerialMode` | Serial |
| `0x04` | `SetLedRunwayMode` | Runway |
| `0x05` | `SetLedOneColorMode` | One Color |
| `0x06` | `SetLedBlockStackingMode` | Block Stacking |

> Careful: the `LightingMode` enum in the code is the order of the **UI combo box**
> (Rainbow=0, Runway=1, OneColor=2, Seria=3, Customize=4, BreathingLight=5,
> BlockStacking=6) and does **not** match the value on the wire. Only the table above
> applies.

## The "response" register is not optional

Every animated mode has, besides its speed, a register the app calls *response* (`0x11`
Runway, `0x13` One Color, `0x16` Serial, `0x18` Rainbow). Measured on hardware: **without
it the mode lights up but does not animate.** Selecting Rainbow and writing only mode,
brightness and speed gives a frozen rainbow; writing `0x18 = 0x02` sets it moving.

What it actually does remains unexplained — only that it has to be written. Both the driver
and `tools/lumi-led.py` always send a mode's full parameter set on a mode change, using the
vendor defaults.

Speed, on the other hand, is confirmed: `0x19` visibly changes the rainbow's pace.

## Initialisation sequence

`<InitializeAsync>d__29::MoveNext` builds a 6-byte array from a static initialiser
`3E 00 0F 00 27 0E` and overwrites indices 1 and 3:

```
[0x3E, brightness, 0x0F, bypass, 0x27, 0x0E]

brightness = 0x88  if lighting is enabled in ledmode_config.json, else 0x00
bypass     = 0x01  if enabled in bypass_config.json, else 0x00
```

In other words: **turning the lighting off means writing brightness zero** (`0x3E 0x00`).
There is no separate enable register.

The application keeps state in `ledmode_config.json` and `bypass_config.json` next to the
executable — as far as can be seen here, nothing is persisted in firmware.

## Factory defaults

Every mode starts at brightness `0x88` (136 of 255). Beyond that:

```
Rainbow:       response 2,  speed 5
Runway:        response 10, interval 1, chaser 1
OneColor:      speed 10
Serial:        response 2,  speed 16
BlockStacking: speed 10
Breathing:     tempo 6
```

## How this maps onto OpenRGB

The card has **no per-LED direct mode**: every effect is generated in firmware. The driver
exposes:

- **Static** → mode `0x01` plus colour in `0x1A`/`0x1B`/`0x1C`, brightness in `0x3E`
- **Breathing** → mode `0x02` plus colour in `0xC9`/`0xCA`/`0xCB` and tempo in `0xC8`
- **Rainbow, Serial, Runway, One Color, Block Stacking** → colourless modes with their
  respective speed parameters

A single zone, one global colour. `MODE_COLORS_MODE_SPECIFIC` for Static and Breathing,
`MODE_COLORS_NONE` for the rest.

## The card has 14 LEDs

`0x27` is the LED count. Measured with Block Stacking, which lights one point at a time:
with `0x27` set to 4, 7 and 14 the effect fills in 4, 7 and 14 steps, exactly. And 14 is
the number of points you can count on the strip.

This is why changing the register *looked* like a speed change: on a strip declared
shorter, the cycle closes sooner, which to the eye is indistinguishable from a faster
effect.

The ONIX utility writes `0x27 = 0x0E` at startup and never touches it again. It is not a
user parameter — it is a declaration of the hardware.

**But there is no way to address the LEDs individually** through anything known about the
protocol: the vendor application writes a single colour for the whole strip, and there is
no other path in its binary (all 23 callers of `WriteReadAsync` are catalogued in
`docs/04-windows-app.md`).

## What is still unknown

- The exact meaning of "response" (`0x11`, `0x13`, `0x16`, `0x18`) and the valid range of
  each parameter. The defaults are above; the slider limits live in the BAML inside `.rsrc`
  and were never extracted.
- Whether there is an undocumented path to address the 14 LEDs individually. The vendor
  application has none, and looking would mean writing to unknown registers on a chip that
  also controls the fans and the voltage regulator.

## Per-LED addressing: looked for, not found

The strip holds 14 physically distinct LEDs — you can count them by eye. Even so, there is
no known way to give each one its own colour.

**What was tested.** If `0xC9`–`0xCB` (the Breathing colour) were LED 0 of a buffer, the 14
LEDs would occupy `0xC9`–`0xF2`, which fits exactly in the free space. With the whole strip
green, `0xFF` was written to the hypothetical red channels — `0xCC`, `0xCF`, `0xD2`, `0xD5`,
`0xD8`, `0xDB`, `0xDE`, `0xE1`, `0xE4`, `0xE7`, `0xEA`, `0xED`, `0xF0` — in three stages,
with temperature watched throughout.

**Result: nothing changed.** The strip stayed green from start to finish, and the
temperature held steady at 56 °C for the whole operation. There is no per-LED buffer in
that arrangement.

**Why the search stopped here.** The evidence converges on the firmware simply not offering
it:

- The ONIX utility, the only software that exists for this card, writes **one colour for
  the entire strip**. All 23 callers of `WriteReadAsync` are catalogued
  (`docs/04-windows-app.md`) and none writes more than that. It would be odd for the vendor
  not to use the most marketable feature of an ARGB card if it existed.
- The most plausible register arrangement tested negative.
- A bulk transfer would need framing different from `(register, value)` pairs, and there is
  no way to guess that without a lead.

Going further would mean writing blind into roughly 130 unknown registers of a chip that
controls the fans and the voltage regulator, with no hypothesis to guide the search. The
ratio of risk to probability does not justify it.

Anyone picking this up again needs a **new source of evidence** — the AMC firmware, a newer
ONIX utility, or vendor documentation. Blind writing is not the way.
