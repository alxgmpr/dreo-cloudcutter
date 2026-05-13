#!/usr/bin/env python3
"""Wrap an RBL firmware file in an OTAU container for HeFi OTA upload."""

import hashlib
import struct
import sys


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def make_otau(rbl_path: str, output_path: str,
              product_id: int = 0x142B293711D19001,
              version: tuple = (9, 9, 9),
              min_version: tuple = (0, 0, 0)):
    with open(rbl_path, 'rb') as f:
        firmware = f.read()

    md5 = hashlib.md5(firmware).digest()
    fw_size = len(firmware)

    header = bytearray(128)
    # Magic
    header[0:4] = b'OTAU'
    # Reserved/flags
    header[4:8] = b'\x00\x00\x00\x00'
    # Product ID (big-endian, 8 bytes)
    struct.pack_into('>Q', header, 0x08, product_id)
    # Firmware size (big-endian)
    struct.pack_into('>I', header, 0x10, fw_size)
    # Target version at 0x19 (3 bytes: major.minor.patch)
    header[0x19] = version[0]
    header[0x1A] = version[1]
    header[0x1B] = version[2]
    # Min upgrade version at 0x1D
    header[0x1D] = min_version[0]
    header[0x1E] = min_version[1]
    header[0x1F] = min_version[2]
    # MD5 hash of firmware body
    header[0x20:0x30] = md5
    # CRC16 of first 126 bytes
    crc = crc16(bytes(header[:126]))
    struct.pack_into('>H', header, 0x7E, crc)

    with open(output_path, 'wb') as f:
        f.write(bytes(header))
        f.write(firmware)

    print(f'OTAU container: {output_path}')
    print(f'  Magic: OTAU')
    print(f'  Product ID: 0x{product_id:016X}')
    print(f'  FW size: {fw_size} bytes')
    print(f'  Version: {version[0]}.{version[1]}.{version[2]}')
    print(f'  Min version: {min_version[0]}.{min_version[1]}.{min_version[2]}')
    print(f'  MD5: {md5.hex()}')
    print(f'  Header CRC16: 0x{crc:04X}')
    print(f'  Total size: {128 + fw_size} bytes')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f'Usage: {sys.argv[0]} <input.rbl> <output.otau>')
        sys.exit(1)
    make_otau(sys.argv[1], sys.argv[2])
