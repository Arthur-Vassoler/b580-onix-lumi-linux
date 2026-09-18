# 01 — Hardware survey

System: Fedora 44, kernel 7.2.5-200.fc44.x86_64, `xe` driver.

## The card

```
04:00.0 VGA compatible controller [0300]: Intel Corporation Battlemage G21 [Arc B580] [8086:e20b]
	Subsystem: Device [207e:a002]          <- 207e = ONIX Technology
	Kernel driver in use: xe
05:00.0 Audio device [0403]: Intel Corporation Device [8086:e2f7]
	Subsystem: Device [207e:a002]
```

PCI ID `207e:a002` identifies the ONIX LUMI variant, and it is what the OpenRGB driver
matches on.

## Where the LED is **not**

**Not USB.** `lsusb` shows nothing behind the card. The only HIDs present are peripherals
and `0b05:19af ASUSTek AURA LED Controller`, which belongs to the **motherboard**. That
rules out the most common arrangement for RGB graphics cards: an onboard USB MCU, the way
ASUS and MSI do it.

**Not the motherboard SMBus.** Scanning `i2c-16` (`SMBus I801 adapter at 0000:80:1f.4`):

```
50: -- UU -- UU -- -- -- --  ...
```

Only the memory modules' SPD EEPROMs (`UU` means claimed by a kernel driver). Nothing from
the GPU. That rules out the route OpenRGB uses for ASUS and Gigabyte cards, over the PCIe
slot's SMBus pins.

## Where the LED **is**

The GPU exposes ten I²C buses of its own:

| bus | name | role |
|---|---|---|
| i2c-3..i2c-11 | `i915 gmbus dpa..tc4` | DDC for the display connectors |
| **i2c-15** | **`Synopsys DesignWare I2C adapter`** | **the card's internal bus** |
| i2c-16 | `SMBus I801` | motherboard, not the GPU |

`i2c-15` is a DesignWare controller the `xe` driver instantiates
(`drivers/gpu/drm/xe/xe_i2c.c`) as `i2c_designware.1024`, a direct child of `0000:04:00.0`.
It is not DDC — it is the card's own service bus.

Scanning i2c-15: **exactly one device, at `0x28`.**

```
20: -- -- -- -- -- -- -- -- 28 -- -- -- -- -- -- --
```

And the kernel already knows what it is:

```
/sys/.../i2c_designware.1024/i2c-15/15-0028/name      -> amc
/sys/.../i2c_designware.1024/i2c-15/15-0028/modalias  -> i2c:amc
/sys/.../i2c_designware.1024/i2c-15/15-0028/driver    -> (does not exist)
```

**AMC = Add-in card Management Controller**, the card's management microcontroller. `xe`
instantiates it with `I2C_CLIENT_HOST_NOTIFY` and handles its SMBus alerts
(`xe_amc_handle_alert`), but **binds no driver to it** — so the address is free for
userspace access through `/dev/i2c-15`.

The AMC is also the target of `xe`'s late binding firmware (`xe_late_bind_fw.c`, sysfs
attributes `lb_fan_control_version` and `lb_voltage_regulator_version` on the GPU), which
confirms it drives the fans and the voltage regulator — and makes it the natural candidate
for the lighting too.

## Permissions

No root needed. `systemd-logind` grants the local session user a `uaccess` ACL:

```
# file: dev/i2c-15
user:arthur:rw-
```

## First probe (read only)

```
SMBus receive byte        -> 0xfe
read byte data 0x00..0x05 -> 0xfe
                    0x06  -> 0x01
                    0x07  -> 0x01
             0x08..0x0e   -> 0xfe
                    0x0f  -> 0x01
```

The device acknowledges and answers. The dominant `0xfe` with occasional `0x01` suggests a
**command/response protocol** rather than a flat register map — `0xFE` probably meaning "no
response pending" or "unsupported command" for any read that does not follow a valid
command.

No I²C errors in `dmesg` after these reads.

## Conclusion

The path is **`/dev/i2c-15`, address `0x28`, the AMC's protocol**. What is missing is the
command set, which comes from analysing the Windows application (see `docs/04`).

## Risk

The AMC controls the fans and the voltage regulator. Writing unknown commands can stop the
cooling. Any write test has to run with `/sys/class/hwmon/hwmon*/fan[123]_input` and the
temperature inputs watched in parallel.
