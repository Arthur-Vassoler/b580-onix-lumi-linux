# 06 — Hardware validation

Carried out on 2026-09-18, Fedora 44, kernel 7.2.5, on an ONIX LUMI Arc B580
(`207e:a002`), after the reboot that freed the wedged bus.

## Result

**The protocol works.** Full control of the lighting from Linux, without root, without a
kernel driver, without the vendor's software.

## The rule that nearly cost the project

The first commands were sent like this, everything in one packet:

```
10 01 1a ff 1b 00 1c 00 3e 88      # Custom mode + red + brightness
```

The AMC **accepted** it (echoed the last value, no I²C error) and the **lighting went
dark**. Two attempts, same result. Split into three separate transactions 50 ms apart, it
worked first try:

```
10 01              # mode
    (50 ms)
3e 88              # brightness
    (50 ms)
1a ff 1b 00 1c 00  # colour
```

Which is what the official application had been doing all along, and I had not noticed:
**every method of `LightingController` writes exactly one command.** `SetLedCustomMode`
sends only `10 01`; `SetCustomColor` sends only the three colours; `LedBrightness` sends
only `3e v`. The one place it batches is the init sequence — and there is no mode change
there.

**Rule: never batch a mode change with other registers.** Safer still: one logical
operation per transaction, like the app.

Why this happens is not established. The likeliest explanation is that the mode change is
processed asynchronously in firmware and overwrites whatever follows — but that was never
proven. What is established is that 50 ms of separation is enough.

## Confirmed

| | |
|---|---|
| Channel order | `0x1A` = **R**, `0x1B` = **G**, `0x1C` = **B**, confirmed visually |
| Custom mode | `0x10` = `0x01` shows a fixed colour |
| Rainbow mode | `0x10` = `0x00` shows the animated rainbow |
| Brightness | `0x3E`, `0x00` is off, `0x88` is the default, `0xFF` works |
| Reply byte | **echo of the last value written**, not a status — `3e 88` returns `88`, `10 05` returns `05` |
| Fast updates | 120 colour writes at 20 Hz, zero I²C errors |
| Fans and temperature | untouched; the 0→700 RPM cycling observed is the idle zero-RPM hysteresis |

## Brightness appears to be per mode

Entering a mode for the first time leaves the lighting dark until `0x3E` is written in that
mode. This matches the application, which keeps a separate brightness field for each mode
(`RainbowBrightness`, `CustomizeBrightness`, `OneColorBrightness`...), all defaulting to
`0x88`. That is why `tools/lumi-led.py` always writes brightness after a mode change.

## Implication for OpenRGB

The 20 Hz with no errors shows a **Direct** mode is viable: write only `1a R 1b G 1c B`,
never touching the mode register, once Custom mode is already active. That is what allows
syncing with the rest of the machine.

## Bus state

No wedging at any point during the whole test run — dozens of transactions, including the
120-colour sweep. A one-byte read immediately after a write is safe; what took the bus down
earlier was an 8-byte read with nothing pending (`docs/03-pitfalls.md`).

## OpenRGB driver validation

Built against upstream master (`0129e58`) with gcc 16.2 and Qt 6.11, on Fedora 44.

```
$ ./openrgb --list-devices
0: ONIX LUMI Intel Arc B580
1: ASUS ROG STRIX B860-G GAMING WIFI
```

The bus resolution patch shows its effect in the detection log:

```
Registering I2C interface: Synopsys DesignWare I2C adapter (/dev/i2c-15) \
    Device 8086:E20B Subsystem: 207E:A002
```

Without it that bus would come up with vendor and device zeroed, and no
`REGISTER_I2C_PCI_DETECTOR` would match.

All eight modes were exercised from OpenRGB's command line and all responded: Static,
Direct, Rainbow, Chroma Flow, Taxiway Glow, Stacking, Breathing and One Color.

### Three defects that only surfaced on building and running

1. **`zone::matrix_map` is no longer a pointer** in current OpenRGB; assigning `NULL` does
   not compile.
2. **The destructor has to call `Shutdown()`.** Without it the base class complains on
   every exit: *"Device thread still active in base class destructor"*.
3. **Animated modes came up frozen.** The driver wrote mode, brightness and speed, but not
   the *response* register — which is what sets the effect in motion.

None of the three would have shown up in a code review. That is the difference between
writing a driver and having one.

## Post-delivery audit

Run after calling the project finished, and it found things.

### An active defect I had left in the repository

There was a probe tool, `tools/amc-probe.py`, from the start of the project — from when the
protocol was still unknown. It swept `0x00..0xff` with `read_byte_data` **by default**.
Since the AMC expects `(register, value)` pairs, that is 256 half-finished writes in a row:
exactly the pattern that preceded the wedged bus early on. Anyone who cloned the repository
and ran it could take the card down and need a reboot.

The sweep was first put behind a `--sweep` flag, and then the tool was removed altogether:
with the protocol now known (`docs/05`), the AMC has no readable register map, so the sweep
was both risky **and** meaningless. What it had that was useful, `tools/survey.sh` does
better.

`tools/amc-mctp.py` stayed, because it documents a real kernel protocol nobody else has
written in Python — but since it never ran against hardware and does a 32-byte read, it
requires `AMC_MCTP_EXPERIMENTAL=1`.

### The mode was rewritten on every colour update

`DeviceUpdateLEDs()` re-applied the whole mode for animated modes. Because OpenRGB calls
`DeviceUpdateMode()` and then `DeviceUpdateLEDs()` right after, every mode change wrote
`0x10` twice about 200 ms apart, restarting the effect. Now only the colour registers are
touched; modes that generate their own colours in firmware write nothing.

This came up while investigating an **intermittent** freeze of the Rainbow mode — two
occurrences, neither reproducible on demand. The double mode write is the likeliest cause,
but that is not proven: what can be said is that after the fix, eight consecutive mode
switches passed without failure.

### Speed range

The first version exposed `0x00..0xFF` "because the register is 8 bits", without testing.
Measured afterwards: the values 1, 2, 3, 5, 8, 12, 16, 24, 31, 32, 40 and 64 all keep the
effect running. The driver now stops at 64, which is as far as the evidence goes.

The perceptible difference across that range is subtle, and it was not possible to tell
whether a higher value means faster or slower. The parameter is exposed but not
characterised.

### Confirmed in this round

- **Brightness through OpenRGB** (`--brightness 20` against `255`): clear difference.
- **Direct entered from an animated mode**: switches into Custom correctly and stops the
  animation. The gap I suspected did not exist.
- **`tools/lumi-led.py` after being changed**: Rainbow animates.

## Second audit: code quality

A pass looking for duplication, dead code and drift between the two implementations.

**The register maps agree.** All 21 registers and all 7 mode values match between
`tools/lumi-led.py` and the C++ header. The duplication is inherent to having two
implementations in two languages; `docs/05-led-protocol.md` is the single source of truth
if they ever diverge.

**The driver never declared the strip length.** `ONIX_REG_STRIP_LENGTH` was defined and
never written: the driver trusted whatever state the card was in. That is not theoretical
— the experiments in this document left `0x27` at 4 and then 7. The driver now writes it
on detection, and the fix was verified by deliberately setting the strip to 4 LEDs,
confirming Block Stacking filled in 4 steps, then letting OpenRGB detect the card and
watching it fill all 14 again.

It still does not write brightness or bypass, which the vendor tool also sets at startup.
Brightness would override the user's last choice, and bypass is a user preference.

**Half of `amc.py` was dead, and the dead half was the dangerous half.** Ten of sixteen
`I2CBus` methods were never called. Several of them — `read_byte_data`, `read_word_data`,
`write_byte_data` and the block variants — write a single byte and then read, which is
exactly the half-finished transaction documented in `docs/03-pitfalls.md` as what wedges
this device. The same class of hazard that had already been removed with `amc-probe.py`
was sitting in the library every tool imports.

With them went the whole SMBus layer that existed only to serve them: `_smbus`, the
`i2c_smbus_*` structures and around ten constants. The module went from 237 lines to 112,
and what remains is what is actually used: locate the device, raw write, raw read.

**Smaller removals:** `SetDirection()` in the driver (register `0x14` is not exposed as an
OpenRGB control), `blob()` in the metadata reader, `VENDOR_ONIX` and `CTRL_CMDS` in the
MCTP tool. `main()` in `lumi-led.py` was 103 lines building transactions inline; the
building moved to `build_transactions()` and `main()` is now 62.

Re-running the audit afterwards found no remaining unused method or constant in either
implementation. Every tool was re-tested, and the card was exercised through static
colour, rainbow, breathing and stacking with no regression.
