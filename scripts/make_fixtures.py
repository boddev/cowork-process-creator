"""Render synthetic ordered screenshot fixtures without imaging dependencies."""
from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

FONT = {
    " ": (0, 0, 0, 0, 0, 0, 0), "-": (0, 0, 0, 31, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 12, 12), ":": (0, 12, 12, 0, 12, 12, 0),
    "/": (1, 2, 2, 4, 8, 8, 16), "(": (2, 4, 8, 8, 8, 4, 2),
    ")": (8, 4, 2, 2, 2, 4, 8), "=": (0, 0, 31, 0, 31, 0, 0),
    "0": (14, 17, 19, 21, 25, 17, 14), "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 2, 4, 8, 31), "3": (30, 1, 1, 14, 1, 1, 30),
    "4": (2, 6, 10, 18, 31, 2, 2), "5": (31, 16, 16, 30, 1, 1, 30),
    "6": (14, 16, 16, 30, 17, 17, 14), "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14), "9": (14, 17, 17, 15, 1, 1, 14),
    "A": (14, 17, 17, 31, 17, 17, 17), "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14), "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31), "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 15), "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (14, 4, 4, 4, 4, 4, 14), "J": (7, 2, 2, 2, 18, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17), "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17), "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14), "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13), "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30), "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14), "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 21, 10), "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4), "Z": (31, 1, 2, 4, 8, 16, 31),
}
WIDTH, HEIGHT = 1200, 640


def png(lines: list[tuple[int, int, str, tuple]], step: str) -> bytes:
    pixels = bytearray(bytes((244, 247, 250)) * WIDTH * HEIGHT)

    def rectangle(x: int, y: int, width: int, height: int, color: tuple) -> None:
        for row in range(y, y + height):
            offset = (row * WIDTH + x) * 3
            pixels[offset:offset + width * 3] = bytes(color) * width

    def label(x: int, y: int, value: str, color: tuple, scale: int = 3) -> None:
        for character in value:
            for row, bits in enumerate(FONT[character]):
                for col in range(5):
                    if bits & (1 << (4 - col)):
                        rectangle(x + col * scale, y + row * scale, scale, scale, color)
            x += 6 * scale

    rectangle(0, 0, WIDTH, 76, (38, 70, 105))
    label(32, 25, "N00 FILE REPORT DEMO (SYNTHETIC)", (255, 255, 255))
    label(32, 110, step, (38, 70, 105))
    for x, y, value, color in lines:
        label(x, y, value, color)
    label(32, 595, "SYNTHETIC EVIDENCE - NO BUSINESS SYSTEM OR CREDENTIALS", (83, 97, 115), scale=2)
    rows = b"".join(b"\x00" + pixels[row * WIDTH * 3:(row + 1) * WIDTH * 3] for row in range(HEIGHT))

    def chunk(kind: bytes, content: bytes) -> bytes:
        return struct.pack(">I", len(content)) + kind + content + struct.pack(">I", zlib.crc32(kind + content) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


def write_if_new_or_same(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != content:
            raise FileExistsError(f"Refusing to replace changed artifact: {path}")
    else:
        with path.open("xb") as handle:
            handle.write(content)


def write_fixtures(output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    dark, green, amber = (35, 47, 61), (0, 110, 66), (146, 83, 0)
    fixtures = [
        ("01-source-inventory.png", "STEP 1: READ INVENTORY", [
            (32, 165, "REPORTING MONTH: 2026-08", dark),
            (32, 220, "ID       STATE    QTY     UNIT COST", dark),
            (32, 265, "R101     READY      2         12.50", green),
            (32, 310, "R102     HOLD       5          3.10", amber),
            (32, 355, "R103     READY      3          7.20", green),
            (32, 400, "R104     READY      1          4.05", green),
            (32, 510, "SCREEN NOTE: LANTERN-42", dark),
        ]),
        ("02-retained-calculations.png", "STEP 2: FILTER AND REPEAT CALCULATION", [
            (32, 175, "KEEP STATE = READY. EXCLUDE R102 (HOLD).", dark),
            (32, 250, "R101      2 X 12.50 = 25.00", green),
            (32, 305, "R103      3 X  7.20 = 21.60", green),
            (32, 360, "R104      1 X  4.05 =  4.05", green),
            (32, 445, "REPEAT FOR EVERY RETAINED ROW.", dark),
            (32, 500, "PRESERVE INPUT ORDER.", dark),
        ]),
        ("03-report-result.png", "STEP 3: CREATE MARKDOWN REPORT", [
            (32, 175, "READY-ITEMS-2026-08.MD", dark),
            (32, 230, "ID       QTY     UNIT COST     LINE COST", dark),
            (32, 275, "R101       2         12.50         25.00", dark),
            (32, 315, "R103       3          7.20         21.60", dark),
            (32, 355, "R104       1          4.05          4.05", dark),
            (32, 430, "INCLUDED ROWS: 3    EXCLUDED ROWS: 1", dark),
            (32, 495, "GRAND TOTAL: 50.65", green),
        ]),
    ]
    paths = []
    for name, step, lines in fixtures:
        path = output / name
        write_if_new_or_same(path, png(lines, step))
        paths.append(path)
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for fixture_path in write_fixtures(args.output):
        print(fixture_path)
