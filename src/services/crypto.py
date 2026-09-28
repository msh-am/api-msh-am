"""
Crypto utility for Meshtastic packet decryption using the default community PSK.
"""

from __future__ import annotations

import logging
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

from meshtastic.protobuf import mesh_pb2

logger = logging.getLogger("msh_am.crypto")

# Default Meshtastic PSK for public channels (AQ== / 1)
DEFAULT_CHANNEL_KEY = bytes([
    0xd4, 0xf1, 0xbb, 0x3a, 0x20, 0x29, 0x07, 0x59,
    0xf0, 0xbc, 0xff, 0xab, 0xcf, 0x4e, 0x69, 0x01
])


def try_decrypt_mesh_packet(packet: mesh_pb2.MeshPacket) -> bool:
    """
    Attempt to decrypt packet.encrypted with default community key into packet.decoded.
    Returns True if successfully decrypted or already decoded, False otherwise.
    """
    if packet.HasField("decoded"):
        return True

    if not packet.encrypted or not HAS_CRYPTO:
        return False

    from_num = getattr(packet, "from")
    packet_id = packet.id

    if not from_num or not packet_id:
        return False

    try:
        # Meshtastic AES-CTR nonce layout (16 bytes):
        # Bytes 0-7:  packet_id as uint64, Little-Endian
        # Bytes 8-11: from_node as uint32, Little-Endian
        # Bytes 12-15: 4 null bytes (counter starts at 0, Big-Endian)
        nonce = packet_id.to_bytes(8, "little") + from_num.to_bytes(4, "little") + b"\x00" * 4
        cipher = Cipher(algorithms.AES(DEFAULT_CHANNEL_KEY), modes.CTR(nonce), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_bytes = decryptor.update(packet.encrypted) + decryptor.finalize()

        decoded = mesh_pb2.Data()
        decoded.ParseFromString(decrypted_bytes)
        packet.decoded.CopyFrom(decoded)
        logger.info(f"Successfully decrypted packet {packet_id} from {from_num:08x} (portnum={decoded.portnum})")
        return True
    except Exception as e:
        # Expected for packets encrypted with a private secondary channel PSK
        logger.debug(f"Could not decrypt packet {packet_id} using default key (private channel?): {e}")
        return False
