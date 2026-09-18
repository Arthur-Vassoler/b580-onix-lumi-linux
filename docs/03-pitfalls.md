# 03 — Pitfalls (learned the hard way)

## A raw I²C read *out of context* wedges the AMC until the next boot

**What happened.** After a successful `i2cdetect` and a series of `read_byte_data` calls, a
raw I²C read was issued — `I2C_RDWR` with a single `I2C_M_RD` message, with no request
pending:

```python
bus.raw_read(0x28, 8)   # -> OSError errno 110 (ETIMEDOUT)
```

From then on **every** access to `0x28` timed out, and a fresh `i2cdetect -y -r 15` showed
an empty bus. It did not recover on its own over 30 seconds. Nothing in `dmesg`.

**Why.** The raw read is legitimate in itself — it is exactly what the kernel driver does
(`i2c_master_recv`, see `docs/02-amc-protocol.md`). The mistake was the **context**: the AMC
is an MCTP endpoint and only has a response to hand over after receiving a well-formed
request and waiting 20 ms. Asking an endpoint for bytes with nothing queued left it stuck
mid-transaction, holding SDA low. With SDA low the entire bus is dead — the DesignWare
controller is fine, it is the slave that will not release the line.

**Refinement, after learning the LED protocol.** The AMC expects `(register, value)` pairs
(see `docs/05-led-protocol.md`). The sweep that preceded the wedge used `read_byte_data`,
which in practice writes **one** byte and reads — 256 half-finished pairs back to back. That
had probably already left the device mid-transaction, and the raw read finished the job. A
practical rule follows: **never write an odd number of bytes** to this device.

**How to recover.** `tools/recover-bus.sh` (needs root) tries, in order, forcing runtime PM
to `on` and then unbinding and rebinding the `i2c_designware` driver. If the AMC really is
holding SDA, nothing in userspace helps — only a power cycle.

**Rule.** Only do a raw read immediately after a complete write. Use
`tools/lumi-led.py`, which pairs request and response correctly. `raw_read()` survives in
the code purely as documentation and requires `i_know_the_risk=True`.

## The I²C controller goes into runtime suspend

`/sys/.../i2c_designware.1024/power/runtime_status` reads `suspended` when idle. That is
normal and the driver resumes it on transfer — do not confuse it with a wedged bus. The
symptom that matters for diagnosis is `i2cdetect` coming back empty.

## The AMC is not a flat register map

Sweeping `0x00..0xff` with `read_byte_data` returned almost all `0xfe`, with `0x01` at
`0x06`, `0x07` and `0x0f`. On a second pass the receive byte returned `0x01` where it had
returned `0xfe` before — the answer depends on **state**, not on the address being read.

Confirmed in `docs/02-amc-protocol.md`: **there are no registers** in the readable sense.
The AMC is an MCTP endpoint. What `read_byte_data` was doing was writing one byte (the
"register") and reading one back — sending truncated MCTP packets and reading responses
that did not exist. `0xFE`/`0x01` is noise, not data.

## The AMC controls the fans and the voltage regulator

Confirmed by the `xe` driver's late binding firmware attributes in the GPU's sysfs
(`lb_fan_control_version`, `lb_voltage_regulator_version`). Unknown write commands can stop
the cooling. Any write test has to run with `fan*_input` and `temp*_input` watched in
parallel.
