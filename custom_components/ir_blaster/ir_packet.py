"""IR packet builder and IR code format utilities for Tuya MCU serial protocol.

Confirmed working from UART analysis:
  Single SerialSend5 with DP7 raw code packet fires IR.
  Header: 55 AA 00 06 00 54 07 00 00 50
  Followed by 80 bytes of IR code
  Followed by checksum byte

IR Code Format
--------------
The 80-byte blob is a sequence of up to 80 uint8 timing values, each representing
a pulse or gap duration in units of 50 microseconds. Values are stored in order
(first value = leading pulse, second = leading gap, ...) and zero-padded at the end.

This module handles three code representations:

  raw hex   - The 80-byte (or shorter) hex string as captured from the device.
              This is what is stored in persistent storage and what the device
              sends back during learn mode. Example:
                "B45A0B0B0B220B22..."

  pulse list - Python list of integer microsecond timings, as used by the
               rc_encoder / pulse / manchester libraries.

  code string - Human-readable protocol string as used by rc_encoder:
                "nec:addr=0xDE,cmd=0xED"
                "samsung32:addr=0x07,cmd=0x02"
                "raw:9000,4500,560,560,560,1690,..."
                "tuya:<base64>"   (passed through as-is, not via MCU path)
"""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

# DP7 header: cmd 06, DP7 raw, total-length 0x0054 (84 bytes = 4 hdr + 80 data), data-length 0x0050 (80 bytes)
_DP7_HEADER = bytes([0x55, 0xAA, 0x00, 0x06, 0x00, 0x54, 0x07, 0x00, 0x00, 0x50])

# Each timing unit in the raw 80-byte blob = 50 microseconds
_TIMING_UNIT_US = 50

# The fixed payload size the MCU expects
_PAYLOAD_BYTES = 80


# ---------------------------------------------------------------------------
# Pulse <-> raw hex conversion
# ---------------------------------------------------------------------------

def pulses_to_hex(pulses: list[int]) -> str:
    """Convert a list of microsecond timing values to a raw hex string.

    Each timing is scaled to _TIMING_UNIT_US units and stored as a uint8.
    Values that would overflow uint8 (>12750 us) are clamped to 255.
    The result is zero-padded to _PAYLOAD_BYTES bytes.

    Returns an uppercase hex string of exactly _PAYLOAD_BYTES * 2 characters.
    """
    scaled = [min(255, round(v / _TIMING_UNIT_US)) for v in pulses]
    padded = (scaled + [0] * _PAYLOAD_BYTES)[:_PAYLOAD_BYTES]
    return bytes(padded).hex().upper()


def hex_to_pulses(hex_code: str) -> list[int] | None:
    """Convert a raw hex string back to a list of microsecond timing values.

    Strips trailing zero values (padding). Returns None if hex_code is invalid.
    """
    clean = hex_code[2:] if hex_code.startswith("0x") else hex_code
    try:
        b = bytes.fromhex(clean)
    except ValueError:
        return None
    timings = list(b)
    while timings and timings[-1] == 0:
        timings.pop()
    return [v * _TIMING_UNIT_US for v in timings]


# ---------------------------------------------------------------------------
# Code string <-> raw hex conversion
# ---------------------------------------------------------------------------

def decode_hex_to_str(hex_code: str) -> str:
    """Attempt to decode a raw hex IR code to a human-readable protocol string.

    Returns a string like "nec:addr=0xDE,cmd=0xED" on success, or
    "raw:9000,4500,560,..." if no known protocol matches.
    Returns the original hex_code unchanged if conversion fails entirely.
    """
    try:
        from .rc_encoder import rc_auto_decode
    except ImportError:
        _LOGGER.warning("rc_encoder not available; cannot decode IR protocol")
        return hex_code

    pulses = hex_to_pulses(hex_code)
    if not pulses:
        return hex_code
    try:
        return rc_auto_decode(pulses)
    except Exception as err:
        _LOGGER.debug("Protocol decode failed: %s", err)
        return hex_code


def encode_str_to_hex(code_str: str) -> str | None:
    """Convert a protocol code string or raw timing string to a raw hex blob.

    Accepts:
      - "nec:addr=0xDE,cmd=0xED"
      - "raw:9000,4500,560,560,560,1690,..."
      - A plain raw hex string (returned as-is after normalisation)

    Returns an uppercase hex string, or None if encoding fails.
    """
    if not code_str:
        return None

    # Plain hex passthrough -- already in device format
    clean = code_str[2:] if code_str.startswith("0x") else code_str
    if _looks_like_hex(clean):
        return clean.upper()

    try:
        from .rc_encoder import rc_auto_encode
    except ImportError:
        _LOGGER.warning("rc_encoder not available; cannot encode protocol string")
        return None

    try:
        result = rc_auto_encode(code_str)
    except ValueError as err:
        _LOGGER.error("Failed to encode IR code string %r: %s", code_str, err)
        return None

    # rc_auto_encode returns a list of pulse ints, or a raw base64 string for "tuya:" format
    if isinstance(result, str):
        _LOGGER.error(
            "tuya: base64 format is not supported by this device; "
            "use nec/raw/other protocol format instead"
        )
        return None

    return pulses_to_hex(result)


def _looks_like_hex(s: str) -> bool:
    """Return True if s looks like a raw hex string (no colons, all hex chars)."""
    s = s.strip()
    return bool(s) and ":" not in s and all(c in "0123456789abcdefABCDEF" for c in s)


# ---------------------------------------------------------------------------
# Packet builder
# ---------------------------------------------------------------------------

def build_send_payload(hex_code: str) -> str | None:
    """Build the SerialSend5 payload for a given IR code.

    Accepts:
      - A raw hex string (80 bytes or shorter)
      - A protocol string like "nec:addr=0xDE,cmd=0xED"
      - A raw timing string like "raw:9000,4500,..."

    Returns the full packet as an uppercase hex string with checksum,
    or None if the code is invalid or cannot be encoded.
    """
    if not hex_code:
        return None

    hex_code = hex_code.strip()

    # If it contains a colon it's a protocol/raw string -- encode it first
    if ":" in hex_code:
        encoded = encode_str_to_hex(hex_code)
        if encoded is None:
            return None
        hex_code = encoded

    clean = hex_code[2:] if hex_code.startswith("0x") else hex_code
    try:
        code_bytes = bytes.fromhex(clean)
    except ValueError:
        _LOGGER.error("Invalid hex code: %s", hex_code)
        return None

    # Pad or truncate to exactly _PAYLOAD_BYTES
    if len(code_bytes) < _PAYLOAD_BYTES:
        code_bytes = code_bytes + bytes(_PAYLOAD_BYTES - len(code_bytes))
    elif len(code_bytes) > _PAYLOAD_BYTES:
        _LOGGER.warning(
            "IR code is %d bytes, truncating to %d", len(code_bytes), _PAYLOAD_BYTES
        )
        code_bytes = code_bytes[:_PAYLOAD_BYTES]

    pkt = _DP7_HEADER + code_bytes
    checksum = sum(pkt) & 0xFF
    return pkt.hex().upper() + f"{checksum:02X}"
