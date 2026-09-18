"""
Low level access to the Arc B580's AMC (Add-in card Management Controller).

No external dependencies — talks to /dev/i2c-N through the i2c-dev ioctls.

    from amc import I2CBus, find_amc
    bus_n, addr = find_amc()
    with I2CBus(bus_n) as bus:
        bus.raw_write(addr, bytes([0x3E, 0x88]))

Deliberately minimal. The AMC speaks (register, value) pairs written as one raw
I2C transaction, so a raw write and a raw read are all that is needed. The SMBus
helpers this module used to carry were removed: none of them was called, and
several of them — read_byte_data and friends — write a single byte and then read,
which is exactly the half-finished transaction that wedges this device
(docs/03-pitfalls.md). Convenience is not worth shipping that as a loaded gun.
"""
from __future__ import annotations

import ctypes
import fcntl
import glob
import os

# i2c-dev ioctls (uapi/linux/i2c-dev.h)
I2C_RDWR = 0x0707

I2C_M_RD = 0x0001


class i2c_msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16),
                ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16),
                ("buf", ctypes.POINTER(ctypes.c_uint8))]


class i2c_rdwr_ioctl_data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(i2c_msg)),
                ("nmsgs", ctypes.c_uint32)]


def find_amc():
    """Locate the bus and address of the 'amc' client the xe driver instantiates.

    Returns (bus_number, addr), or raises RuntimeError.
    """
    for dev in glob.glob("/sys/bus/i2c/devices/*-[0-9a-f]*"):
        name_path = os.path.join(dev, "name")
        if not os.path.exists(name_path):
            continue
        try:
            with open(name_path) as fh:
                if fh.read().strip() != "amc":
                    continue
        except OSError:
            continue
        base = os.path.basename(dev)          # e.g. "15-0028"
        bus_s, _, addr_s = base.partition("-")
        return int(bus_s), int(addr_s, 16)
    raise RuntimeError("no 'amc' i2c client found - is the GPU bound to the xe driver?")


class I2CBus:
    """Thin wrapper around /dev/i2c-N, raw transfers only."""

    def __init__(self, bus: int):
        self.bus = bus
        self.path = f"/dev/i2c-{bus}"
        self.fd = os.open(self.path, os.O_RDWR)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def raw_write(self, addr: int, payload: bytes):
        """Write `payload` as a single I2C transaction."""
        buf = (ctypes.c_uint8 * len(payload))(*payload)
        msg = i2c_msg(addr=addr, flags=0, len=len(payload), buf=buf)
        self._xfer([msg])

    def raw_read(self, addr: int, length: int, i_know_the_risk: bool = False) -> bytes:
        """Raw I2C read, with no command byte.

        Safe only immediately after a complete write, which is how the vendor's
        software uses it. On its own, with nothing queued, it leaves the AMC out
        of sync holding SDA low: the whole bus stops responding and only a power
        cycle brings it back. See docs/03-pitfalls.md.

        Requires an explicit opt-in so it cannot be reached by accident.
        """
        if not i_know_the_risk:
            raise RuntimeError(
                "raw_read() is only safe right after a complete write. On its "
                "own it wedges the Arc B580's AMC until the card is power "
                "cycled. If that is what you mean, pass i_know_the_risk=True.")
        buf = (ctypes.c_uint8 * length)()
        msg = i2c_msg(addr=addr, flags=I2C_M_RD, len=length, buf=buf)
        self._xfer([msg])
        return bytes(buf)

    def _xfer(self, msgs):
        arr = (i2c_msg * len(msgs))(*msgs)
        data = i2c_rdwr_ioctl_data(msgs=arr, nmsgs=len(msgs))
        fcntl.ioctl(self.fd, I2C_RDWR, data)
