#!/usr/bin/env python3
"""Tuya MCU protocol decoder. Parses 55 AA framed packets."""

import sys
import time
import argparse
from datetime import datetime

TUYA_COMMANDS = {
    0x00: "Heartbeat",
    0x01: "Query Product Info",
    0x02: "Query Working Mode",
    0x03: "WiFi Status Report",
    0x04: "WiFi Reset (E&AP)",
    0x05: "WiFi Reset (AP)",
    0x06: "WiFi Status Query",
    0x07: "Query DP Status",
    0x08: "DP Command (issue)",
    0x09: "DP Status Report",
    0x0A: "DP Query",
    0x0E: "OTA Start",
    0x0F: "OTA Data",
    0x10: "Get System Time (GMT)",
    0x1C: "Get System Time (Local)",
}

DP_TYPES = {
    0x00: "Raw",
    0x01: "Bool",
    0x02: "Value (int32)",
    0x03: "String",
    0x04: "Enum",
    0x05: "Bitmap",
}


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def parse_dp(data: bytes, offset: int = 0):
    """Parse a single Tuya datapoint from data at offset. Returns (dp_dict, bytes_consumed)."""
    if offset + 4 > len(data):
        return None, 0
    dp_id = data[offset]
    dp_type = data[offset + 1]
    dp_len = (data[offset + 2] << 8) | data[offset + 3]
    if offset + 4 + dp_len > len(data):
        return None, 0
    dp_value_raw = data[offset + 4 : offset + 4 + dp_len]

    type_name = DP_TYPES.get(dp_type, f"Unknown(0x{dp_type:02x})")

    if dp_type == 0x01 and dp_len == 1:
        value = bool(dp_value_raw[0])
    elif dp_type == 0x02 and dp_len == 4:
        value = int.from_bytes(dp_value_raw, "big", signed=True)
    elif dp_type == 0x04 and dp_len == 1:
        value = dp_value_raw[0]
    elif dp_type == 0x05:
        value = int.from_bytes(dp_value_raw, "big")
    elif dp_type == 0x03:
        try:
            value = dp_value_raw.decode("ascii")
        except Exception:
            value = dp_value_raw.hex(" ")
    else:
        value = dp_value_raw.hex(" ")

    dp = {
        "id": dp_id,
        "type": type_name,
        "type_id": dp_type,
        "len": dp_len,
        "value": value,
        "raw": dp_value_raw.hex(" "),
    }
    return dp, 4 + dp_len


def parse_packet(packet: bytes):
    """Parse a complete Tuya MCU packet (including 55 AA header)."""
    if len(packet) < 7:
        return None

    version = packet[2]
    cmd = packet[3]
    data_len = (packet[4] << 8) | packet[5]
    data = packet[6 : 6 + data_len]
    pkt_checksum = packet[6 + data_len] if len(packet) > 6 + data_len else None

    expected_cs = checksum(packet[:-1])
    cs_ok = pkt_checksum == expected_cs if pkt_checksum is not None else None

    cmd_name = TUYA_COMMANDS.get(cmd, f"Unknown(0x{cmd:02x})")

    result = {
        "version": version,
        "command": cmd,
        "command_name": cmd_name,
        "data_len": data_len,
        "data": data,
        "checksum_ok": cs_ok,
        "checksum_expected": expected_cs,
        "checksum_actual": pkt_checksum,
    }

    if cmd == 0x01 and data_len > 0:
        try:
            result["product_info"] = data.decode("ascii", errors="replace")
        except Exception:
            pass

    if cmd in (0x07, 0x08, 0x09, 0x0A) and data_len > 0:
        dps = []
        off = 0
        while off < len(data):
            dp, consumed = parse_dp(data, off)
            if dp is None:
                break
            dps.append(dp)
            off += consumed
        result["datapoints"] = dps

    return result


def extract_packets(raw: bytes):
    """Extract all 55 AA packets from a byte stream."""
    packets = []
    i = 0
    while i < len(raw) - 6:
        if raw[i] == 0x55 and raw[i + 1] == 0xAA:
            data_len = (raw[i + 4] << 8) | raw[i + 5]
            pkt_len = 6 + data_len + 1  # header(6) + data + checksum(1)
            if i + pkt_len <= len(raw):
                pkt = raw[i : i + pkt_len]
                packets.append((i, pkt))
                i += pkt_len
                continue
        i += 1
    return packets


def format_packet(offset, packet, parsed):
    lines = []
    cs_marker = "OK" if parsed["checksum_ok"] else f"FAIL (got 0x{parsed['checksum_actual']:02x}, expected 0x{parsed['checksum_expected']:02x})"
    lines.append(
        f"[offset 0x{offset:04x}] {parsed['command_name']} (cmd=0x{parsed['command']:02x}, "
        f"ver={parsed['version']}, len={parsed['data_len']}, checksum={cs_marker})"
    )
    lines.append(f"  raw: {packet.hex(' ')}")

    if "product_info" in parsed:
        lines.append(f"  product: {parsed['product_info']}")

    if "datapoints" in parsed:
        for dp in parsed["datapoints"]:
            lines.append(
                f"  DP id={dp['id']:3d} (0x{dp['id']:02x})  type={dp['type']:<14s}  value={dp['value']}  [{dp['raw']}]"
            )

    return "\n".join(lines)


def decode_hex_string(hex_str: str):
    """Decode a hex string (space-separated or continuous)."""
    clean = hex_str.replace(" ", "").replace("\n", "").replace("\r", "")
    raw = bytes.fromhex(clean)
    packets = extract_packets(raw)

    if not packets:
        print("No valid 55 AA packets found.")
        return

    print(f"Found {len(packets)} packet(s):\n")
    for offset, pkt in packets:
        parsed = parse_packet(pkt)
        if parsed:
            print(format_packet(offset, pkt, parsed))
            print()


def live_capture(port: str, baud: int = 115200):
    """Live serial capture and decode."""
    import serial

    ser = serial.Serial(port, baud, timeout=0.1)
    print(f"Listening on {port} @ {baud} baud. Ctrl+C to stop.\n")

    buf = bytearray()
    try:
        while True:
            chunk = ser.read(256)
            if chunk:
                buf.extend(chunk)
                packets = extract_packets(bytes(buf))
                for offset, pkt in packets:
                    parsed = parse_packet(pkt)
                    if parsed:
                        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(f"[{ts}] {format_packet(offset, pkt, parsed)}")
                        print()
                if packets:
                    last_offset, last_pkt = packets[-1]
                    end = last_offset + len(last_pkt)
                    buf = buf[end:]
            else:
                time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tuya MCU Protocol Decoder")
    sub = parser.add_subparsers(dest="mode")

    dec = sub.add_parser("decode", help="Decode hex string")
    dec.add_argument("hex", nargs="?", help="Hex string to decode (or reads stdin)")

    cap = sub.add_parser("capture", help="Live serial capture")
    cap.add_argument("port", help="Serial port (e.g. /dev/tty.usbserial-2120)")
    cap.add_argument("-b", "--baud", type=int, default=115200)

    args = parser.parse_args()

    if args.mode == "decode":
        if args.hex:
            decode_hex_string(args.hex)
        else:
            decode_hex_string(sys.stdin.read())
    elif args.mode == "capture":
        live_capture(args.port, args.baud)
    else:
        parser.print_help()
