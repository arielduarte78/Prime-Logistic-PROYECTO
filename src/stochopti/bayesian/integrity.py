"""stochopti/bayesian/integrity.py — Cadena de Integridad HMAC-SHA256."""

import hashlib
import hmac
import logging
import struct
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger("IntegrityChain")

_GENESIS_HASH = b"\x00" * 32

@dataclass(frozen=True)
class IntegrityEntry:
    """Entrada inmutable en la cadena de integridad."""
    seq: int
    timestamp_utc: str
    event_type: str
    payload_digest: str
    previous_hash: str
    entry_hash: str


class IntegrityChain:
    """
    Cadena de integridad HMAC-SHA256 encadenada para audit trail
    de mutaciones bayesianas.
    """

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError(
                "HMAC key must be at least 32 bytes (256 bits). "
                f"Received {len(key)} bytes."
            )
        self._key = bytearray(key)
        self._entries: List[IntegrityEntry] = []
        self._last_hash: bytes = _GENESIS_HASH
        self._lock = threading.Lock()
        self._compromised = False

        logger.info("IntegrityChain initialized.")

    @property
    def compromised(self) -> bool:
        return self._compromised

    def append(self, event_type: str, payload_digest: bytes) -> int:
        with self._lock:
            seq = len(self._entries)
            timestamp = datetime.now(timezone.utc).isoformat()
            previous_hash_hex = self._last_hash.hex()
            payload_digest_hex = payload_digest.hex()

            message = struct.pack(">I", seq)
            message += event_type.encode("utf-8")
            message += payload_digest
            message += self._last_hash

            entry_hash = hmac.new(
                bytes(self._key), message, hashlib.sha256
            ).digest()

            entry = IntegrityEntry(
                seq=seq,
                timestamp_utc=timestamp,
                event_type=event_type,
                payload_digest=payload_digest_hex,
                previous_hash=previous_hash_hex,
                entry_hash=entry_hash.hex(),
            )

            self._entries.append(entry)
            self._last_hash = entry_hash

            return seq

    def verify_chain(self) -> bool:
        with self._lock:
            prev_hash = _GENESIS_HASH

            for entry in self._entries:
                message = struct.pack(">I", entry.seq)
                message += entry.event_type.encode("utf-8")
                message += bytes.fromhex(entry.payload_digest)
                message += prev_hash

                expected_hash = hmac.new(
                    bytes(self._key), message, hashlib.sha256
                ).digest()

                if expected_hash.hex() != entry.entry_hash:
                    logger.critical(
                        "INTEGRITY BREACH DETECTED at seq=%d event=%s.",
                        entry.seq, entry.event_type
                    )
                    self._compromised = True
                    return False

                prev_hash = expected_hash

            return True

    def get_last_hash(self) -> bytes:
        with self._lock:
            return bytes(self._last_hash)

    def get_chain_length(self) -> int:
        return len(self._entries)

    def export_audit_trail(self) -> List[dict]:
        with self._lock:
            return [
                {
                    "seq": e.seq,
                    "timestamp_utc": e.timestamp_utc,
                    "event_type": e.event_type,
                    "payload_digest": e.payload_digest,
                    "previous_hash": e.previous_hash,
                    "entry_hash": e.entry_hash,
                }
                for e in self._entries
            ]

    def sanitize_key(self) -> None:
        with self._lock:
            for i in range(len(self._key)):
                self._key[i] = 0
