# 02 — The AMC protocol

Primary source: `drivers/gpu/drm/xe/xe_amc.c` in the Linux kernel (Copyright 2026 Intel).
This is not reverse engineering — it is Intel's own driver, with the packet layout spelled
out.

## The AMC speaks MCTP over SMBus

Not a register map. It is **MCTP** (DMTF DSP0236) carried over SMBus (DSP0237), with the
message body being **Vendor Defined – PCI** (type `0x7E`) from Intel.

That is why the register sweep only ever returned `0xfe`: there are no registers to read.

## Request layout

```c
struct amc_header {          /* 7 bytes */
    u8 command;              /* 0x0F — MCTP over SMBus command code       */
    u8 len;                  /* byte count: total packet minus 2          */
    u8 address;              /* 0x8F — source address (the host)          */
    u8 version;              /* 0x01 — MCTP header version                */
    u8 destination;          /* 12   — destination EID (the AMC)          */
    u8 source;               /* 8    — source EID (the host)              */
    u8 flags;                /* 0xC8 — SOM|EOM|TO, seq 0, tag 0           */
};

struct amc_message {         /* 4 bytes */
    u8  type;                /* 0x7E — Vendor Defined PCI                 */
    u16 vendor;              /* 0x8086 big endian (Intel)                 */
    u8  command;             /* vendor specific command                   */
};

struct amc_request  { amc_header; amc_message; u32 reserved; };   /* 15 bytes */
struct amc_response { amc_header; amc_message; u8 error; u8 value; }; /* 13 bytes */
```

`flags = 0xC8` decodes as SOM=1, EOM=1, seq=0, TO=1, tag=0 — a single packet expecting a
response. Textbook MCTP.

`len = sizeof(request) - 2 = 13`: everything after the byte count field itself (5 header
bytes + 4 message bytes + 4 reserved).

## How the transaction runs

```c
i2c_master_send(client, request, 15);   /* raw I2C write, 15 bytes        */
fsleep(20 * USEC_PER_MSEC);             /* the AMC needs 20 ms            */
i2c_master_recv(client, response, 13);  /* raw I2C read, 13 bytes         */
```

Three details that matter:

1. **These are not i2c-dev SMBus transactions.** It is a raw write followed by a raw read,
   with `0x0F` as the first payload byte rather than an SMBus command code.
2. **The 20 ms are not optional.** Reading earlier returns garbage, or nothing.
3. **No PEC.** The client is not created with `I2C_CLIENT_PEC`.

The driver validates the response by comparing `response.message` against
`request.message` byte for byte — the AMC echoes type, vendor and command back. A useful
canary for whether a command was accepted.

## The only documented command

```c
#define AMC_MSG_TYPE         0x7e
#define AMC_GET_ALERT_REASON 0x01
```

A non-zero `error` in the response means the command was rejected. `value` carries the
alert reason:

| value | meaning |
|---|---|
| 0 | unknown |
| 1 | Firmware Download |
| 2 | Thermal Trip |
| 3 | OOB Request |
| 4 | OOB Reset |
| 5 | Catastrophic |

## Why this unblocked the project

The search space stopped being "256 opaque registers" and became "the `command` byte inside
a well-formed vendor-defined message". Better still, MCTP comes with **standard
discovery**. Control messages (type `0x00`) include:

| cmd | what it does |
|---|---|
| 0x02 | Get Endpoint ID |
| 0x03 | Get Endpoint UUID |
| 0x04 | Get MCTP Version Support |
| 0x05 | Get Message Type Support |
| 0x06 | **Get Vendor Defined Message Support** |

`0x06` returns **which vendor IDs the endpoint serves**. If ONIX had hung LED control off a
vendor-defined message of their own (PCI vendor `0x207E`) rather than Intel's, that command
would show it. All of it is read-only, specified by standard, and free of side effects.

## Important: MCTP is not the LED channel

This document describes the **alert** channel the `xe` driver uses. Analysis of the Windows
application (`docs/04-windows-app.md`) showed the LED uses something else at the same
address: direct writes of `(register, value)` pairs, with no MCTP framing at all
(`docs/05-led-protocol.md`).

The two coexist at `0x28`. Note that the MCTP over SMBus command code is `0x0F`, which is
also the LED's *bypass* register — an apparent collision that was never investigated. When
in doubt, send `0x0F` together with its value, the way the vendor application does.

## References

- `drivers/gpu/drm/xe/xe_amc.c`, `xe_i2c.c`, `xe_i2c.h` — Linux kernel
- DMTF DSP0236 — MCTP Base Specification
- DMTF DSP0237 — MCTP SMBus/I2C Transport Binding
