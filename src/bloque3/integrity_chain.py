# src/bloque3/integrity_chain.py
"""
Cadena de Integridad HMAC-SHA256 para Audit Trail Inmutable de Priors Bayesianos.

ISO 27001 Control A.12.4 — Registro y Monitoreo.

Cada entrada de la cadena firma criptográficamente:
  - El número de secuencia monotónico
  - El tipo de evento (INIT, UPDATE_EDGE, STOCHASTIC_OVERRIDE, KEY_ROTATION)
  - El digest del estado mutado
  - El hash de la entrada anterior

La cadena es append-only. Cualquier adulteración de una entrada intermedia
invalida todas las entradas posteriores al recalcular.

CISO Directive: Se usa big-endian (>) en struct.pack para garantizar
portabilidad entre arquitecturas de servidor.
"""

import hashlib
import hmac
import logging
import struct
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger("IntegrityChain")

# Sentinel para el bloque génesis
_GENESIS_HASH = b"\x00" * 32


@dataclass(frozen=True)
class IntegrityEntry:
    """Entrada inmutable en la cadena de integridad."""
    seq: int
    timestamp_utc: str
    event_type: str
    payload_digest: str  # hex-encoded SHA-256 del estado mutado
    previous_hash: str   # hex-encoded hash de la entrada anterior
    entry_hash: str      # hex-encoded HMAC-SHA256 de esta entrada


class IntegrityChain:
    """
    Cadena de integridad HMAC-SHA256 encadenada para audit trail
    de mutaciones bayesianas.

    Thread-safe: todas las operaciones de escritura están protegidas
    por un lock. Las lecturas son seguras porque las entradas son inmutables.
    """

    def __init__(self, key: bytes) -> None:
        """
        Args:
            key: Clave HMAC de al menos 32 bytes. Se almacena como
                 bytearray mutable para permitir sanitización al shutdown.
        """
        if len(key) < 32:
            raise ValueError(
                "HMAC key must be at least 32 bytes (256 bits). "
                f"Received {len(key)} bytes."
            )
        # Almacenar como bytearray mutable para poder sanitizar en shutdown
        self._key = bytearray(key)
        self._entries: List[IntegrityEntry] = []
        self._last_hash: bytes = _GENESIS_HASH
        self._lock = threading.Lock()
        self._compromised = False

        logger.info("IntegrityChain initialized (key loaded, genesis sentinel set).")

    @property
    def compromised(self) -> bool:
        """True si se detectó una violación de integridad."""
        return self._compromised

    def append(self, event_type: str, payload_digest: bytes) -> int:
        """
        Añade una entrada firmada a la cadena.

        Args:
            event_type: Tipo de evento (INIT, UPDATE_EDGE, STOCHASTIC_OVERRIDE).
            payload_digest: SHA-256 digest (raw bytes, 32 bytes) del estado mutado.

        Returns:
            Número de secuencia de la entrada creada.
        """
        with self._lock:
            seq = len(self._entries)
            timestamp = datetime.now(timezone.utc).isoformat()
            previous_hash_hex = self._last_hash.hex()
            payload_digest_hex = payload_digest.hex()

            # Construir el mensaje a firmar con endianness explícito (big-endian)
            # CISO Directive: usar > (big-endian / network byte order)
            message = struct.pack(">I", seq)  # 4 bytes, big-endian unsigned int
            message += event_type.encode("utf-8")
            message += payload_digest
            message += self._last_hash

            # HMAC-SHA256 con la clave activa
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

            if seq % 100 == 0 and seq > 0:
                logger.debug(
                    "IntegrityChain: %d entries logged, last event=%s",
                    seq, event_type
                )

            return seq

    def verify_chain(self) -> bool:
        """
        Verifica la integridad completa de la cadena recalculando
        cada HMAC desde el génesis.

        Returns:
            True si toda la cadena es íntegra, False si hay adulteración.
        """
        with self._lock:
            prev_hash = _GENESIS_HASH

            for entry in self._entries:
                # Reconstruir el mensaje exacto
                message = struct.pack(">I", entry.seq)
                message += entry.event_type.encode("utf-8")
                message += bytes.fromhex(entry.payload_digest)
                message += prev_hash

                expected_hash = hmac.new(
                    bytes(self._key), message, hashlib.sha256
                ).digest()

                if expected_hash.hex() != entry.entry_hash:
                    logger.critical(
                        "INTEGRITY BREACH DETECTED at seq=%d event=%s. "
                        "Expected hash=%s, stored hash=%s",
                        entry.seq, entry.event_type,
                        expected_hash.hex()[:16] + "...",
                        entry.entry_hash[:16] + "..."
                    )
                    self._compromised = True
                    return False

                prev_hash = expected_hash

            return True

    def get_last_hash(self) -> bytes:
        """Retorna el último hash de la cadena (raw bytes)."""
        with self._lock:
            return bytes(self._last_hash)

    def get_chain_length(self) -> int:
        """Retorna el número de entradas en la cadena."""
        return len(self._entries)

    def export_audit_trail(self) -> List[dict]:
        """
        Exporta la cadena completa como lista de dicts para auditoría forense.
        """
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
        """
        Sobrescribe la clave en memoria con ceros. Llamar al shutdown.
        Después de esto, append() y verify_chain() fallarán.
        """
        with self._lock:
            for i in range(len(self._key)):
                self._key[i] = 0
            logger.info("IntegrityChain: HMAC key sanitized from memory.")
