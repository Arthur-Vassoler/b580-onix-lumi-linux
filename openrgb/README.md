# OpenRGB driver for the ONIX LUMI Intel Arc B580

Lighting support for the card in OpenRGB. The protocol is documented in
[`../docs/05-led-protocol.md`](../docs/05-led-protocol.md) and was validated on hardware
([`../docs/06`](../docs/06-hardware-validation.md)).

## Files

```
Controllers/OnixArcController/
    OnixArcController.h            register map and mode constants
    OnixArcController.cpp          I2C transactions
    RGBController_OnixArc.h
    RGBController_OnixArc.cpp      zones, modes and effects
    OnixArcControllerDetect.cpp    detection by PCI ID

patches/
    0001-pci_ids-add-onix-arc-b580.patch
    0002-i2c-linux-walk-up-to-pci-parent.patch
```

## Why the two patches

**`0001`** only adds identifiers: `INTEL_ARC_B580_DEV` (`0xE20B`), `ONIX_SUB_VEN`
(`0x207E`) and `ONIX_LUMI_ARC_B580` (`0xA002`).

**`0002`** is a real fix, and it matters beyond this card. OpenRGB resolves the I²C
adapter's real path and truncates it **once** to reach the parent PCI device. That works
for AMD GPUs, where the adapter is a direct child of the PCI device:

```
/sys/devices/pci.../0000:03:00.0/i2c-4        ->  0000:03:00.0   ✔
```

On Arc, the adapter sits behind an intermediate platform device:

```
/sys/devices/pci.../0000:04:00.0/i2c_designware.1024/i2c-15
                                 ^^^^^^^^^^^^^^^^^^^ stops here, no vendor/device
```

The bus ends up registered with vendor and device zeroed, and no
`REGISTER_I2C_PCI_DETECTOR` matches. The patch keeps walking up until it reaches a
directory holding a `vendor` file. It is generic: any GPU that exposes I²C through an
intermediate device becomes detectable.

## Building

Dependencies on Fedora 44 — `qt6-linguist` is easy to forget, and the build only fails on
it near the end, while compiling translations:

```sh
sudo dnf install -y gcc-c++ make qt6-qtbase-devel qt6-linguist \
                    libusb1-devel hidapi-devel mbedtls-devel
```

```sh
git clone https://gitlab.com/CalcProgrammer1/OpenRGB.git
cd OpenRGB
git apply /path/to/openrgb/patches/0001-*.patch
git apply /path/to/openrgb/patches/0002-*.patch
cp -r /path/to/openrgb/Controllers/OnixArcController Controllers/
qmake6 OpenRGB.pro && make -j$(nproc)
./openrgb --list-devices
```

No root needed: `systemd-logind` grants the local session user an ACL on `/dev/i2c-*`.

The new files are picked up automatically — `OpenRGB.pro` globs `Controllers/*/*.cpp`.

## What the driver exposes

One zone, one LED. The strip holds 14 LEDs, but the card generates every effect in
firmware and offers no individual addressing, so a single LED is the honest representation
rather than 14 that always match.

| OpenRGB mode | register `0x10` | colours |
|---|---|---|
| Direct | `0x01` | per LED |
| Static | `0x01` | mode specific |
| Breathing | `0x02` | mode specific |
| Rainbow | `0x00` | none |
| Chroma Flow | `0x03` | none |
| Taxiway Glow | `0x04` | none |
| One Color | `0x05` | none |
| Stacking | `0x06` | none |

**Direct** works because, once Custom mode is active, it is enough to rewrite the colour
registers — measured at 20 Hz with no I²C errors. The driver avoids touching the mode
register on that path, otherwise the effect restarts on every frame.

## On detection

The driver writes the strip length (`0x27 = 0x0E`, 14 LEDs) as soon as the card is
detected. The register is what tells the firmware how many LEDs the effects span, and it
persists: a card left declaring a shorter strip would run every effect over part of it,
with nothing in OpenRGB to put it right.

It deliberately does **not** write the other two registers the vendor tool sets at startup.
Brightness would override whatever the user last chose, and bypass hands the strip to the
motherboard's ARGB header — a user preference this driver has no business flipping on
detection.

## Two hardware constraints, encoded in the driver

1. **Never batch a mode change with other registers in one transaction.** The card accepts
   the packet and goes dark. One logical operation per transaction, 50 ms apart.
2. **Brightness has to be reapplied after a mode change** — a mode entered for the first
   time comes up dark.

## Status

Built against upstream master (`0129e58`) with gcc 16.2 and Qt 6.11, and validated on
hardware: the card appears as `ONIX LUMI Intel Arc B580` and all eight modes respond.

Not submitted upstream yet. Both patches apply cleanly to master.

## Not yet verified

- What speed actually does. Values 1 through 64 were checked and all keep the effect
  running, but the perceptible difference is subtle and it is unclear whether higher means
  faster or slower. The driver stops at 64, which is as far as the evidence goes.
- The other modes' parameters were not characterised; they use the vendor defaults.
- An intermittent Rainbow freeze was observed twice before `DeviceUpdateLEDs` stopped
  rewriting the mode. It has not recurred since, but it was never reproducible on demand
  either — the cause is not proven.
