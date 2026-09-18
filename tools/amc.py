"""
Acesso de baixo nível ao AMC (Add-in card Management Controller) da Arc B580.

Sem dependências externas — fala com /dev/i2c-N direto pelos ioctls do i2c-dev.

    from amc import I2CBus, find_amc
    bus, addr = find_amc()
    with I2CBus(bus) as b:
        print(hex(b.read_byte(addr)))

Tudo aqui é leitura por padrão. Os métodos de escrita existem, mas quem chama
precisa saber o que está fazendo: o AMC também controla ventoinha e VRM.
"""
from __future__ import annotations

import ctypes
import fcntl
import glob
import os

# ioctls do i2c-dev (uapi/linux/i2c-dev.h)
I2C_SLAVE = 0x0703
I2C_SLAVE_FORCE = 0x0706
I2C_FUNCS = 0x0705
I2C_RDWR = 0x0707
I2C_PEC = 0x0708
I2C_SMBUS = 0x0720

I2C_M_RD = 0x0001

I2C_SMBUS_WRITE = 0
I2C_SMBUS_READ = 1

(I2C_SMBUS_QUICK, I2C_SMBUS_BYTE, I2C_SMBUS_BYTE_DATA, I2C_SMBUS_WORD_DATA,
 I2C_SMBUS_PROC_CALL, I2C_SMBUS_BLOCK_DATA, I2C_SMBUS_I2C_BLOCK_BROKEN,
 I2C_SMBUS_BLOCK_PROC_CALL, I2C_SMBUS_I2C_BLOCK_DATA) = range(9)

I2C_FUNC_BITS = [
    (0x00000001, "I2C"),
    (0x00000002, "10BIT_ADDR"),
    (0x00000004, "PROTOCOL_MANGLING"),
    (0x00000008, "SMBUS_PEC"),
    (0x00008000, "NOSTART"),
    (0x00010000, "SMBUS_QUICK"),
    (0x00020000, "SMBUS_READ_BYTE"),
    (0x00040000, "SMBUS_WRITE_BYTE"),
    (0x00080000, "SMBUS_READ_BYTE_DATA"),
    (0x00100000, "SMBUS_WRITE_BYTE_DATA"),
    (0x00200000, "SMBUS_READ_WORD_DATA"),
    (0x00400000, "SMBUS_WRITE_WORD_DATA"),
    (0x00800000, "SMBUS_PROC_CALL"),
    (0x01000000, "SMBUS_READ_BLOCK_DATA"),
    (0x02000000, "SMBUS_WRITE_BLOCK_DATA"),
    (0x04000000, "SMBUS_READ_I2C_BLOCK"),
    (0x08000000, "SMBUS_WRITE_I2C_BLOCK"),
    (0x10000000, "SMBUS_HOST_NOTIFY"),
]


class i2c_smbus_data(ctypes.Union):
    _fields_ = [("byte", ctypes.c_uint8),
                ("word", ctypes.c_uint16),
                ("block", ctypes.c_uint8 * 34)]  # len + 32 dados + pad


class i2c_smbus_ioctl_data(ctypes.Structure):
    _fields_ = [("read_write", ctypes.c_uint8),
                ("command", ctypes.c_uint8),
                ("size", ctypes.c_uint32),
                ("data", ctypes.POINTER(i2c_smbus_data))]


class i2c_msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16),
                ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16),
                ("buf", ctypes.POINTER(ctypes.c_uint8))]


class i2c_rdwr_ioctl_data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(i2c_msg)),
                ("nmsgs", ctypes.c_uint32)]


def find_amc():
    """Localiza o barramento e o endereço do client 'amc' instanciado pelo xe.

    Retorna (bus_number, addr) ou levanta RuntimeError.
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
        base = os.path.basename(dev)          # ex: "15-0028"
        bus_s, _, addr_s = base.partition("-")
        return int(bus_s), int(addr_s, 16)
    raise RuntimeError("client i2c 'amc' não encontrado — a GPU está com o driver xe?")


class I2CBus:
    """Wrapper fino sobre /dev/i2c-N."""

    def __init__(self, bus: int):
        self.bus = bus
        self.path = f"/dev/i2c-{bus}"
        self.fd = os.open(self.path, os.O_RDWR)
        self._addr = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    # -- infraestrutura -------------------------------------------------

    def funcs(self) -> int:
        val = ctypes.c_ulong()
        fcntl.ioctl(self.fd, I2C_FUNCS, val)
        return val.value

    def funcs_str(self) -> list[str]:
        f = self.funcs()
        return [name for bit, name in I2C_FUNC_BITS if f & bit]

    def _set_addr(self, addr: int, force: bool = False):
        if self._addr != (addr, force):
            fcntl.ioctl(self.fd, I2C_SLAVE_FORCE if force else I2C_SLAVE, addr)
            self._addr = (addr, force)

    def _smbus(self, addr, read_write, command, size, data=None, force=False):
        self._set_addr(addr, force)
        buf = data if data is not None else i2c_smbus_data()
        args = i2c_smbus_ioctl_data(read_write=read_write, command=command,
                                    size=size, data=ctypes.pointer(buf))
        fcntl.ioctl(self.fd, I2C_SMBUS, args)
        return buf

    # -- leituras -------------------------------------------------------

    def read_byte(self, addr: int) -> int:
        """SMBus Receive Byte: só endereça e lê um byte."""
        return self._smbus(addr, I2C_SMBUS_READ, 0, I2C_SMBUS_BYTE).byte

    def read_byte_data(self, addr: int, reg: int) -> int:
        return self._smbus(addr, I2C_SMBUS_READ, reg, I2C_SMBUS_BYTE_DATA).byte

    def read_word_data(self, addr: int, reg: int) -> int:
        return self._smbus(addr, I2C_SMBUS_READ, reg, I2C_SMBUS_WORD_DATA).word

    def read_block_data(self, addr: int, reg: int) -> bytes:
        """SMBus Read Block: o dispositivo informa o tamanho."""
        d = self._smbus(addr, I2C_SMBUS_READ, reg, I2C_SMBUS_BLOCK_DATA)
        n = min(d.block[0], 32)
        return bytes(d.block[1:1 + n])

    def read_i2c_block(self, addr: int, reg: int, length: int) -> bytes:
        """I2C block read: o host dita o tamanho (até 32)."""
        d = i2c_smbus_data()
        d.block[0] = length
        d = self._smbus(addr, I2C_SMBUS_READ, reg, I2C_SMBUS_I2C_BLOCK_DATA, d)
        return bytes(d.block[1:1 + length])

    def raw_read(self, addr: int, length: int, i_know_the_risk: bool = False) -> bytes:
        """Leitura I2C crua (sem byte de comando).

        PERIGO — comprovadamente trava o AMC desta placa. Um read solto, sem o
        byte de comando que ele espera, deixa o dispositivo fora de sincronia
        segurando SDA; o barramento inteiro para de responder e só volta com
        ciclo de energia. Ver docs/03-pitfalls.md.

        Mantido apenas para documentar o comportamento. Exige opt-in explícito.
        """
        if not i_know_the_risk:
            raise RuntimeError(
                "raw_read() trava o AMC da Arc B580 e exige reboot para voltar. "
                "Use write_then_read(). Se realmente quiser, passe "
                "i_know_the_risk=True.")
        buf = (ctypes.c_uint8 * length)()
        msg = i2c_msg(addr=addr, flags=I2C_M_RD, len=length, buf=buf)
        self._xfer([msg])
        return bytes(buf)

    def write_then_read(self, addr: int, out: bytes, length: int) -> bytes:
        """Escreve `out`, faz repeated-start, lê `length` bytes.

        É o padrão de request/response da maioria dos MCUs. ATENÇÃO: isto
        escreve no barramento.
        """
        wbuf = (ctypes.c_uint8 * len(out))(*out)
        rbuf = (ctypes.c_uint8 * length)()
        msgs = [i2c_msg(addr=addr, flags=0, len=len(out), buf=wbuf),
                i2c_msg(addr=addr, flags=I2C_M_RD, len=length, buf=rbuf)]
        self._xfer(msgs)
        return bytes(rbuf)

    # -- escritas (perigoso; ver README) --------------------------------

    def write_byte(self, addr: int, value: int):
        d = i2c_smbus_data()
        d.byte = value
        self._smbus(addr, I2C_SMBUS_WRITE, value, I2C_SMBUS_BYTE, d)

    def write_byte_data(self, addr: int, reg: int, value: int):
        d = i2c_smbus_data()
        d.byte = value
        self._smbus(addr, I2C_SMBUS_WRITE, reg, I2C_SMBUS_BYTE_DATA, d)

    def write_block_data(self, addr: int, reg: int, payload: bytes):
        if len(payload) > 32:
            raise ValueError("bloco SMBus é limitado a 32 bytes")
        d = i2c_smbus_data()
        d.block[0] = len(payload)
        for i, b in enumerate(payload):
            d.block[1 + i] = b
        self._smbus(addr, I2C_SMBUS_WRITE, reg, I2C_SMBUS_BLOCK_DATA, d)

    def raw_write(self, addr: int, payload: bytes):
        buf = (ctypes.c_uint8 * len(payload))(*payload)
        msg = i2c_msg(addr=addr, flags=0, len=len(payload), buf=buf)
        self._xfer([msg])

    def _xfer(self, msgs):
        arr = (i2c_msg * len(msgs))(*msgs)
        data = i2c_rdwr_ioctl_data(msgs=arr, nmsgs=len(msgs))
        fcntl.ioctl(self.fd, I2C_RDWR, data)
