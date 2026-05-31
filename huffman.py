import heapq
import json
import os
from collections import Counter
from dataclasses import dataclass
from itertools import count
from typing import Optional


MAGIC = b"HUF1"


@dataclass
class _Node:
    symbol: Optional[int] = None
    left: Optional["_Node"] = None
    right: Optional["_Node"] = None

    @property
    def is_leaf(self) -> bool:
        return self.symbol is not None


def format_symbol(symbol: int) -> str:
    """Return a readable database/UI label for one byte value."""
    if symbol == 10:
        return "\\n"
    if symbol == 13:
        return "\\r"
    if symbol == 9:
        return "\\t"
    if symbol == 32:
        return "<space>"
    if 33 <= symbol <= 126:
        return chr(symbol)
    return f"0x{symbol:02X}"


def _build_tree(frequency: dict[int, int]) -> Optional[_Node]:
    if not frequency:
        return None

    serial = count()
    heap: list[tuple[int, int, _Node]] = [
        (freq, next(serial), _Node(symbol=symbol))
        for symbol, freq in sorted(frequency.items())
    ]
    heapq.heapify(heap)

    while len(heap) > 1:
        freq_a, _, node_a = heapq.heappop(heap)
        freq_b, _, node_b = heapq.heappop(heap)
        parent = _Node(left=node_a, right=node_b)
        heapq.heappush(heap, (freq_a + freq_b, next(serial), parent))

    return heap[0][2]


def _generate_codes(node: Optional[_Node], prefix: str = "") -> dict[int, str]:
    if node is None:
        return {}
    if node.is_leaf:
        return {node.symbol: prefix or "0"}

    codes: dict[int, str] = {}
    codes.update(_generate_codes(node.left, prefix + "0"))
    codes.update(_generate_codes(node.right, prefix + "1"))
    return codes


def _bits_to_bytes(bits: str) -> tuple[bytes, int]:
    if not bits:
        return b"", 0
    padding = (8 - len(bits) % 8) % 8
    padded = bits + ("0" * padding)
    payload = bytearray()
    for i in range(0, len(padded), 8):
        payload.append(int(padded[i:i + 8], 2))
    return bytes(payload), padding


def _bytes_to_bits(payload: bytes, padding: int) -> str:
    bits = "".join(f"{byte:08b}" for byte in payload)
    if padding:
        return bits[:-padding]
    return bits


def compress_file(input_path: str, output_path: str, original_filename: str = "") -> dict:
    with open(input_path, "rb") as source:
        data = source.read()

    frequency = dict(Counter(data))
    tree = _build_tree(frequency)
    codes = _generate_codes(tree)
    encoded_bits = "".join(codes[byte] for byte in data)
    payload, padding = _bits_to_bytes(encoded_bits)

    header = {
        "version": 1,
        "original_filename": original_filename or os.path.basename(input_path),
        "original_size": len(data),
        "padding": padding,
        "frequency": {str(byte): freq for byte, freq in sorted(frequency.items())},
    }
    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")

    with open(output_path, "wb") as target:
        target.write(MAGIC)
        target.write(len(header_bytes).to_bytes(4, "big"))
        target.write(header_bytes)
        target.write(payload)

    original_size = os.path.getsize(input_path)
    compressed_size = os.path.getsize(output_path)
    space_saved = round((1 - compressed_size / original_size) * 100, 2) if original_size else 0
    ratio = round(original_size / compressed_size, 4) if compressed_size else 1.0

    return {
        "original_size": original_size,
        "compressed_size": compressed_size,
        "space_saved_percent": space_saved,
        "compression_ratio": ratio,
        "total_chars": len(data),
        "total_bits": len(encoded_bits),
        "huffman_codes": codes,
        "frequency_table": frequency,
    }


def decompress_file(input_path: str, output_path: str) -> dict:
    with open(input_path, "rb") as source:
        if source.read(4) != MAGIC:
            raise ValueError("This is not a valid Huffman-compressed file.")

        header_length = int.from_bytes(source.read(4), "big")
        header = json.loads(source.read(header_length).decode("utf-8"))
        payload = source.read()

    frequency = {int(byte): freq for byte, freq in header.get("frequency", {}).items()}
    tree = _build_tree(frequency)
    bits = _bytes_to_bits(payload, int(header.get("padding", 0)))

    if tree is None:
        decoded = b""
    elif tree.is_leaf:
        decoded = bytes([tree.symbol]) * sum(frequency.values())
    else:
        decoded_bytes = bytearray()
        node = tree
        for bit in bits:
            node = node.left if bit == "0" else node.right
            if node.is_leaf:
                decoded_bytes.append(node.symbol)
                node = tree
        decoded = bytes(decoded_bytes)

    with open(output_path, "wb") as target:
        target.write(decoded)

    return {
        "original_filename": header.get("original_filename", ""),
        "compressed_size": os.path.getsize(input_path),
        "decompressed_size": os.path.getsize(output_path),
    }
