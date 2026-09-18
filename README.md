# ONIX LUMI Intel Arc B580 — ARGB lighting on Linux

Reverse engineering of the lighting controller on the **ONIX LUMI Intel Arc B580 12GB**
(PCI `8086:e20b`, subsystem `207e:a002`), and a driver that makes it work with
[OpenRGB](https://openrgb.org).

## The problem

The card has an addressable RGB strip. ONIX ships **LUMI ARGB Control Software** to drive
it — Windows only. On Linux there was nothing: not in OpenRGB, not anywhere else. The
OpenRGB issue asking for Intel Arc B580 support had been open and empty since January 2025.

Intel's own position is that the Arc B580 has no RGB control application; the only Arc card
they shipped lighting software for is the A770 Limited Edition, which uses an entirely
different mechanism (a USB dongle on a motherboard header).

## The result

Full control of the lighting from Linux, no root required, with two front ends:

```sh
# OpenRGB, once the driver is built (see openrgb/README.md)
openrgb --device 0 --mode static --color FF0000

# or the standalone CLI in this repository, no build needed
tools/lumi-led.py color ff0000
tools/lumi-led.py mode rainbow
tools/lumi-led.py off
```

All eight lighting modes work: Static, Direct, Rainbow, Chroma Flow, Taxiway Glow,
Stacking, Breathing and One Color.

## How it works

The LED controller is **not** a USB device and it is **not** on the motherboard SMBus —
the two places RGB graphics cards usually put it. It sits behind the card's **AMC**
(Add-in card Management Controller) on the GPU's own internal I²C bus:

```
/dev/i2c-15   "Synopsys DesignWare I2C adapter"   (the GPU's internal bus)
  └─ 0x28     i2c client "amc", instantiated by the xe driver, no driver bound
```

The protocol is a stream of `(register, value)` pairs written in a single I²C
transaction. Selecting a mode, setting brightness and setting a colour are three separate
transactions:

```
0x10  mode      0x3E  brightness   0x27  strip length (14 LEDs)
0x1A/1B/1C  RGB (Custom)           0xC9/CA/CB  RGB (Breathing)

modes: 00 Rainbow · 01 Custom · 02 Breathing · 03 Serial
       04 Runway · 05 One Color · 06 Block Stacking
```

The full register map is in [`docs/05-led-protocol.md`](docs/05-led-protocol.md).

## Requirements

- An ONIX LUMI Intel Arc B580 (`207e:a002`). Other ONIX cards may share the protocol, but
  none have been tested.
- A kernel with the `xe` driver, which creates the internal I²C bus and its `amc` client.
  Verified on Linux 7.2 / Fedora 44.
- `i2c-tools` for `tools/survey.sh`. Python 3 with no external packages for everything else.

### Bus permissions

No root needed, but only because a udev rule tags the I²C buses for `uaccess`, which is
what makes `systemd-logind` grant the local session user an ACL on them. Check yours:

```sh
getfacl /dev/i2c-15        # should list your user with rw-
```

On Fedora that rule comes from the **`openrgb-udev-rules`** package, which is separate from
`openrgb` itself:

```sh
sudo dnf install openrgb-udev-rules
```

Most distributions ship the same rules under a similar name. The line that matters is:

```
KERNEL=="i2c-[0-99]*", TAG+="uaccess"
```

Worth knowing what that grants: access to **every** I²C bus on the machine, including the
memory modules' SPD EEPROMs on the motherboard SMBus — not just the GPU's. It is the
tradeoff OpenRGB makes so it can find devices without root. A rule scoped to this card
alone is possible (the bus's parent chain carries `ATTRS{vendor}=="0x8086"` and
`ATTRS{device}=="0xe20b"`), but it has not been tested here, so it is not offered as a
recipe.

If you remove the OpenRGB package after building this driver, take care: `openrgb` depends
on `openrgb-udev-rules`, so removing it takes the rules along as an unused dependency, and
everything here starts needing `sudo` after the next reboot. Existing device nodes keep
their ACLs until then, which makes the breakage easy to miss.

## Install

### Option 1 — the standalone CLI

Nothing to build.

```sh
cd b580-onix-lumi-linux
tools/survey.sh              # confirm the AMC shows up at 0x28
tools/lumi-led.py color ff0000
```

### Option 2 — the OpenRGB driver

Needs building OpenRGB from source, because the driver is not upstream yet. Full
instructions, including the Fedora dependency list, are in
[`openrgb/README.md`](openrgb/README.md). In short:

```sh
git clone https://gitlab.com/CalcProgrammer1/OpenRGB.git
cd OpenRGB
git apply /path/to/b580-onix-lumi-linux/openrgb/patches/*.patch
cp -r /path/to/b580-onix-lumi-linux/openrgb/Controllers/OnixArcController Controllers/
qmake6 OpenRGB.pro && make -j$(nproc)
./openrgb --list-devices
```

Note that this builds a **second** OpenRGB. If your distribution also packages one, that
package does not contain this driver, and typing `openrgb` or clicking the desktop icon
will still launch it — the card will not show up there.

To keep both side by side without shadowing the packaged command:

```sh
mkdir -p ~/.local/bin ~/.local/share/applications
ln -sf "$PWD/openrgb" ~/.local/bin/openrgb-onix

cat > ~/.local/share/applications/openrgb-onix.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=OpenRGB (ONIX)
Comment=OpenRGB build with the ONIX LUMI Intel Arc B580 driver
Icon=org.openrgb.OpenRGB
StartupWMClass=openrgb
TryExec=openrgb-onix
Exec=openrgb-onix
Terminal=false
Categories=Utility;
DESKTOP
```

`openrgb-onix` then works from the terminal and appears in the application menu as
"OpenRGB (ONIX)", while `openrgb` keeps meaning the packaged build. Remove both files to
undo.

## Safety

**The AMC also controls the card's fans and voltage regulator.** Writing unknown registers
can stop the cooling. Everything in this repository stays within the register set the
vendor's own software uses, and the tools print GPU fan and temperature readings around
every write.

Two hardware quirks are worth knowing before you experiment, both learned the hard way and
written up in [`docs/03-pitfalls.md`](docs/03-pitfalls.md):

- **Never batch a mode change with other registers in one transaction.** The card accepts
  the packet, echoes it back, and the lighting goes dark.
- **Never read more bytes than the device has to give.** A multi-byte read with nothing
  queued leaves the AMC holding SDA low, and the whole bus stays dead until the card is
  power cycled.

## Documentation

The write-up is the point of this repository as much as the code is. It is meant to be
enough for someone to redo the work, or to port it to another card.

| | |
|---|---|
| [`01-hardware-survey.md`](docs/01-hardware-survey.md) | finding the controller, and ruling out USB and the motherboard SMBus |
| [`02-amc-protocol.md`](docs/02-amc-protocol.md) | the AMC's MCTP alert channel, straight from the kernel driver |
| [`03-pitfalls.md`](docs/03-pitfalls.md) | what wedges the bus, and how to recover |
| [`04-windows-app.md`](docs/04-windows-app.md) | extracting and decompiling the vendor software |
| [`05-led-protocol.md`](docs/05-led-protocol.md) | the complete register map |
| [`06-hardware-validation.md`](docs/06-hardware-validation.md) | what was measured, and what broke on the way |
| [`07-effect-parameters.md`](docs/07-effect-parameters.md) | open: a protocol for working out what the speed registers really do |

## Tools

| | |
|---|---|
| `tools/lumi-led.py` | control the lighting |
| `tools/survey.sh` | hardware inventory: buses, clients, sensors |
| `tools/recover-bus.sh` | when the I²C bus stops responding (needs root) |
| `tools/extract-lumi.py` | unpack the vendor installer |
| `tools/dotnet-il.py` | list and disassemble .NET assemblies |
| `tools/amc-mctp.py` | the AMC's MCTP framing — documentation, never run against hardware |

`tools/dotnet_meta.py` is a minimal ECMA-335 metadata reader, written because Fedora's
`monodis` aborts on the vendor's assembly. `tools/amc.py` talks to `/dev/i2c-*` through
ioctls directly, with no external dependencies.

## Contributing

Reports from other cards are the most useful thing right now. If you have an ONIX card
that is not the LUMI B580, `tools/survey.sh` output plus the PCI subsystem ID tells us
whether the protocol carries over.

Open questions, in rough order of how much they would improve the driver:

- **Per-LED addressing.** The strip has 14 physically distinct LEDs but no known way to
  address them individually. The search so far, and why it stopped, is documented at the
  end of [`docs/05-led-protocol.md`](docs/05-led-protocol.md). Reopening it needs a *new
  source of evidence* — AMC firmware, a newer ONIX utility, vendor documentation — not
  more blind writes.
- **What the "response" registers do.** Without them an effect lights up but never
  animates. That is all that is known.
- **What the speed registers actually do.** Raising `0x19` appears to narrow the rainbow's
  gradient rather than speed it up, which would make it a spatial parameter that the driver
  currently drives from the wrong slider. [`docs/07-effect-parameters.md`](docs/07-effect-parameters.md)
  is a protocol for settling it with measurements instead of impressions.

If you send patches, please keep the OpenRGB driver in OpenRGB's code style, since the
goal is to land it upstream.

## Upstream status

Not submitted yet. The driver and the two patches apply cleanly against OpenRGB master and
are ready to go; see [`openrgb/README.md`](openrgb/README.md).

## Author

<a href="https://github.com/Arthur-Vassoler">
  <img src="https://github.com/Arthur-Vassoler.png" width="120" alt="Arthur Vassoler's GitHub avatar">
</a>

**Arthur Vassoler** — [@Arthur-Vassoler](https://github.com/Arthur-Vassoler)

Reverse engineering of the controller, the OpenRGB driver, the standalone CLI and the
documentation in this repository.

## License

GPL-2.0-or-later, matching OpenRGB.

The vendor software is not redistributed here. `tools/extract-lumi.py` reproduces the
extraction from the installer ONIX publishes; the download is documented in
[`docs/04-windows-app.md`](docs/04-windows-app.md).
