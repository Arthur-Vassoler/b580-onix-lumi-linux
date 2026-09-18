# 04 — The Windows application (LUMI ARGB Control Software v2.1)

Downloaded from `https://cdn.onixsys.com/assets/downloads/LUMISetupV2.1.zip`
(official page: https://onixsys.com/download-en/), version 2.1, 2025-03-17.
The binary is **not** redistributed in this repository — `tools/extract-lumi.py`
reproduces the extraction from the original file.

## How to extract it (Fedora's innoextract will not do)

The installer is Inno Setup **6.3.0**. `innoextract` 1.9, which is what Fedora 44 packages,
dies with `Unexpected setup data version: 6.3.0`. 7-Zip 26 will not open it either.

There is no need to parse Inno's headers. The files sit in a **single solid LZMA1 stream**:

```
0x0c6400:  7a 6c 62 1a  5d 00 00 80 00  ...
           "zlb\x1a"    LZMA1 props (lc3/lp0/pb2, 8 MiB dictionary)
```

Synthesise a `FORMAT_ALONE` header (5 property bytes plus 8 bytes of unknown size) and
decompress: out come 36.8 MiB holding 42 PE executables, which can be carved on the MZ/PE
header and named from the PDB path in their CodeView record.

## The hardware access stack

```
LUMI.exe                (.NET / WPF, MahApps.Metro)
   └─ P/Invoke
OnixI2CDriver.dll       (native x64, 15 KiB — C:\Wrapper\OnixI2CDriver\)
   └─ DeviceIoControl
NfI2cTestDrv.sys        (KMDF, 55 KiB — "ReferenceCode_I2CPeripheralDriver_Tool")
   └─ \Device\RESOURCE_HUB\  (Windows SPB / I2C peripheral)
```

`NfI2cTestDrv.sys` publishes symlinks shaped like:

```
\DosDevices\NF_I2C_BUS_%02X_0X%04X       <- bus number, slave address
```

## The finding that closes the loop

Inside `OnixI2CDriver.dll`, as a literal UTF-16 string:

```
\\.\nf_i2c_bus_00_0x0028
```

**Bus 0, address 0x0028.** Exactly the AMC the Linux scan found on `/dev/i2c-15`. Confirmed
end to end: the ONIX LUMI's lighting is driven **by the AMC**, not by a dedicated MCU.

So there is no path Windows uses that Linux lacks — only the command set was missing.

## The wrapper API

`OnixI2CDriver.dll` exports six functions:

| export | what it does |
|---|---|
| `InitializeDriver` | loads and opens the driver |
| `OpenConnection` | opens `\\.\nf_i2c_bus_00_0x0028` |
| **`WriteReadAsync`** | **writes a buffer, reads the reply** |
| `EnableInterrupts` | enables the SMBus alert |
| `DisableInterrupts` | disables it |
| `CloseConnection` | closes |

Relevant imports: `CreateFileW`, `DeviceIoControl`, `CreateEventW`, `GetOverlappedResult` —
overlapped, asynchronous I/O.

`WriteReadAsync` is precisely the transaction in `xe_amc.c`: a write followed by a read.
And `EnableInterrupts`/`DisableInterrupts` correspond to the same SMBus alert the `xe`
driver handles in `xe_amc_handle_alert()`. The two implementations are talking to the same
device in the same way.

## Where the LED commands live

In `LUMI.exe` (2.5 MiB, a .NET assembly). The member names already give away the data
model:

```
LedMode  LedBrightness  LedDirection  LedModeConfig  ConfigLedModePath
get_RgbColor  get_RGBValue  FormatRGBValue  NormalizeRGBString
InitBreathingMode  InitStackingMode
get_BreathingBrightness  get_BreathingColor  get_BreathingTempo
get_StackingDirection  get_StackingSpeed
get_RunwayChaser  get_RunwayBrightness  get_RainbowBrightness
get_OneColorBrightness  get_SerialBrightness  get_CustomizeBrightness
```

Which line up with the effects ONIX advertises: PrismPulse, Chaser, Breathing, Chroma Flow,
Stacking, Taxiway Glow.

**The packets are not stored as constants in the binary.** Scanning `LUMI.exe` for MCTP
templates (`8f 01 0c 08 c8`, `7e 80 86`, `7e 20 7e`, `0f 0d 8f`) found nothing — the
application builds its buffers in IL, byte by byte. Getting them out meant decompiling the
assembly.

Fedora's `monodis` aborts on this assembly with an assertion in the string heap, so
`tools/dotnet_meta.py` implements an ECMA-335 metadata reader and `tools/dotnet-il.py` an IL
disassembler, both dependency-free. The result is in `docs/05-led-protocol.md`.
