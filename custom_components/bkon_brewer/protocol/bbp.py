"""The `.bbp` menu-file codec — the parts that are confirmed.

The machine's on-board menu is a `.bbp` file loaded over USB, which is how a
recipe escapes the 599-byte Bluetooth ceiling. The format was recovered from
real device files; see docs/BBP_FORMAT.md.

What lives here is only what is verified byte-for-byte against those files: the
container checksum and the step-record codec. The category-table framing is not
yet exact, so this module deliberately does **not** offer "write a whole menu
file" — that would be guessing with a flash write as the consequence. What it
does offer is enough to read the steps out of a real file (including one the
machine exports itself, which is how the rest gets confirmed) and to build the
step section of one.

Pure: bytes in, bytes out. No Home Assistant, no I/O.
"""
from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass

MAGIC_MENU = b"BKON"          # a beverage menu
MAGIC_SERVICE = b"BKOn"       # a service/diagnostic menu (lowercase n)
MAGICS = (MAGIC_MENU, MAGIC_SERVICE)

#: Step type -> the name this project uses. Confirmed: every portion in every
#: sample file opens with exactly one START and closes with exactly one BREW_OUT.
STEP_TYPES = {0: "start", 1: "fr", 2: "vc", 3: "pg", 4: "bo"}
TYPE_CODES = {v: k for k, v in STEP_TYPES.items()}


class BbpError(ValueError):
    """The file is not a .bbp, or is damaged."""


def checksum(body: bytes) -> bytes:
    """The four trailing bytes: JAMCRC, little-endian.

    JAMCRC is CRC-32 with the final complement omitted -- equivalently, the
    bitwise inverse of an ordinary CRC-32. Confirmed against all three sample
    files; nothing else matched.
    """
    return struct.pack("<I", zlib.crc32(body) ^ 0xFFFFFFFF)


def verify(data: bytes) -> bool:
    """Does this file's trailing checksum match its content?"""
    if len(data) < 12 or data[:4] not in MAGICS:
        return False
    return checksum(data[:-4]) == data[-4:]


def seal(body: bytes) -> bytes:
    """Append the checksum to a finished body."""
    return body + checksum(body)


@dataclass(slots=True)
class Step:
    """One step as it sits in the file: a type and its tag string."""

    type_code: int
    tag: str

    @property
    def name(self) -> str:
        return STEP_TYPES.get(self.type_code, f"unknown({self.type_code})")


def encode_step(type_code: int, tag: str) -> bytes:
    """One step record: u32le type, u8 tag length, the tag.

    The tag is the same uppercase XML-ish form the Bluetooth path uses, e.g.
    ``<PS>28</PS><TM>7</TM>``.
    """
    raw = tag.encode("ascii")
    if len(raw) > 255:
        raise BbpError(f"step tag is {len(raw)} bytes; the length field holds 255")
    return struct.pack("<IB", type_code, len(raw)) + raw


def decode_step(data: bytes, offset: int = 0) -> tuple[Step, int]:
    """Read one step record. Returns the step and the offset just past it."""
    if offset + 5 > len(data):
        raise BbpError("truncated step header")
    type_code, length = struct.unpack_from("<IB", data, offset)
    start = offset + 5
    if start + length > len(data):
        raise BbpError("truncated step tag")
    return Step(type_code, data[start:start + length].decode("latin-1")), start + length


#: A well-formed tag string is one or more <NAME>value</NAME> pairs and nothing
#: else. Requiring the closing name to match the opening one is what keeps the
#: scanner off the machine-parameter tag soup at the head of a beverage menu,
#: which is otherwise shaped just like a step payload.
_TAG_RE = re.compile(rb"^(?:<([A-Z]+)>[^<>]*</\1>)+$")


def iter_steps(data: bytes):
    """Every step record in a file, in order, found structurally.

    Scans rather than walking the category table, because that framing is not
    yet exact (docs/BBP_FORMAT.md). A record counts as a step when its type is
    one we know, its three high type bytes are zero, and its payload is a
    complete, balanced tag string of exactly the declared length.

    Being strict here matters: a looser check triples the match count on the
    real files by finding sequences that merely start with "<".
    """
    i, n = 0, len(data)
    while i + 5 <= n:
        type_code = data[i]
        if type_code in STEP_TYPES and data[i + 1:i + 4] == b"\0\0\0":
            length = data[i + 4]
            start = i + 5
            tag = data[start:start + length]
            if length and start + length <= n and _TAG_RE.match(tag):
                yield Step(type_code, tag.decode("latin-1"))
                i = start + length
                continue
        i += 1


def steps_to_tags(steps) -> list[tuple[str, str]]:
    """(step name, tag) pairs — the readable form of iter_steps."""
    return [(s.name, s.tag) for s in steps]
