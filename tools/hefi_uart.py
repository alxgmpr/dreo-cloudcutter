#!/usr/bin/env python3
"""HeFi UART control for Dreo DR-HTF007S WiFi module (BK7231N).

Sends commands over UART to the WiFi module, simulating the CMS80F7518 MCU.
Protocol: 55 AA framing with 8-byte header (HeFi variant of Tuya MCU protocol).

Packet format:
  55 AA [ver=00] [seq] [cmd] [sub=00] [len_hi] [len_lo] [data...] [checksum]
  Checksum = sum(all preceding bytes) & 0xFF
  Min packet = 9 bytes (no data)

Usage:
  python hefi_uart.py /dev/tty.usbserial-2120 provision   # Enter AP/pairing mode
  python hefi_uart.py /dev/tty.usbserial-2120 reset        # Factory reset + AP mode
  python hefi_uart.py /dev/tty.usbserial-2120 status        # Query WiFi status
  python hefi_uart.py /dev/tty.usbserial-2120 monitor       # Monitor UART traffic
  python hefi_uart.py /dev/tty.usbserial-2120 init          # Full MCU init sequence
"""

import serial
import sys
import time
import argparse

PRODUCT_INFO = b'007+CMS89F7518/USA+3.0.6'

CMDS = {
    0x00: 'Heartbeat',
    0x01: 'ProductInfo',
    0x02: 'WorkingMode',
    0x03: 'WiFiStatus',
    0x04: 'Provision',
    0x05: 'ResetAP',
    0x06: 'WiFiStatusQuery',
    0x07: 'DPStatus',
    0x08: 'DPCommand',
    0x09: 'DPReport',
    0x0A: 'DPQuery',
    0x0E: 'DeviceSerial',
    0x10: 'FactoryReset',
    0x11: 'GetVersion',
    0x14: 'Subcommand',
}

WIFI_STATUS = {
    0: 'SmartConfig',
    1: 'AP mode',
    2: 'Connected',
    3: 'Connected+Cloud',
    4: 'Connected+WrongPwd',
}


def make_pkt(seq, cmd, data=b'', sub=0x00):
    p = bytes([0x55, 0xAA, 0x00, seq & 0xFF, cmd, sub,
               len(data) >> 8, len(data) & 0xFF]) + data
    return p + bytes([sum(p) & 0xFF])


def parse_pkts(buf):
    pkts = []
    buf = bytearray(buf)
    while len(buf) >= 9:
        idx = buf.find(b'\x55\xaa')
        if idx == -1:
            buf = buf[-1:]
            break
        if idx > 0:
            buf = buf[idx:]
            continue
        cmd = buf[4]
        dlen = (buf[6] << 8) | buf[7]
        total = 8 + dlen + 1
        if len(buf) < total:
            break
        cs = buf[8 + dlen]
        expected = sum(buf[:8 + dlen]) & 0xFF
        if cs == expected:
            pkts.append({
                'seq': buf[3], 'cmd': cmd, 'sub': buf[5],
                'data': bytes(buf[8:8 + dlen]), 'raw': bytes(buf[:total])
            })
        buf = buf[total:]
    return pkts, bytes(buf)


def fmt_pkt(p):
    name = CMDS.get(p['cmd'], f'0x{p["cmd"]:02x}')
    data_str = p['data'].hex(' ') if p['data'] else '-'
    extra = ''
    if p['cmd'] == 0x03 and p['data']:
        st = p['data'][0]
        extra = f' ({WIFI_STATUS.get(st, f"unknown={st}")})'
    elif p['cmd'] == 0x01 and p['data']:
        try:
            extra = f' ({p["data"].decode("ascii")})'
        except:
            pass
    return f'seq={p["seq"]:02x} {name:15s} data={data_str}{extra}'


def send_and_recv(ser, seq, cmd, data=b'', wait=1.0):
    pkt = make_pkt(seq, cmd, data)
    ser.write(pkt)
    time.sleep(wait)
    raw = ser.read(4096)
    pkts, _ = parse_pkts(raw)
    return pkts


def respond_to(ser, pkts):
    for p in pkts:
        if p['cmd'] == 0x01:
            ser.write(make_pkt(p['seq'], 0x01, PRODUCT_INFO))
            print(f'  >> Product info sent')
        elif p['cmd'] == 0x02:
            ser.write(make_pkt(p['seq'], 0x02, b'\x00'))
            print(f'  >> Working mode sent')
        elif p['cmd'] == 0x00:
            ser.write(make_pkt(p['seq'], 0x00, b'\x01'))


def cmd_provision(ser):
    """Enter AP/pairing mode."""
    print('Sending provision mode (cmd 0x04)...')
    pkts = send_and_recv(ser, 0, 0x04, wait=2)
    for p in pkts:
        print(f'  {fmt_pkt(p)}')
    print('Done. Check WiFi for Dreo AP.')


def cmd_reset(ser):
    """Factory reset (clear WiFi creds) + enter AP mode."""
    print('Factory reset (cmd 0x10)...')
    pkts = send_and_recv(ser, 0, 0x10, wait=2)
    for p in pkts:
        print(f'  {fmt_pkt(p)}')
    respond_to(ser, pkts)

    print('Provision mode (cmd 0x04)...')
    pkts = send_and_recv(ser, 1, 0x04, wait=2)
    for p in pkts:
        print(f'  {fmt_pkt(p)}')

    print('Heartbeating 30s...')
    buf = bytearray()
    start = time.time()
    while time.time() - start < 30:
        ser.write(make_pkt(int(time.time() - start) & 0xFF, 0x00, b'\x01'))
        time.sleep(0.3)
        chunk = ser.read(2048)
        if chunk:
            buf.extend(chunk)
        pkts, buf = parse_pkts(buf)
        for p in pkts:
            print(f'  [{time.time()-start:4.0f}s] {fmt_pkt(p)}')
            respond_to(ser, [p])
        buf = bytearray(buf)
        time.sleep(0.2)
    print('Done. Check WiFi for Dreo AP.')


def cmd_status(ser):
    """Query current WiFi status."""
    print('Querying WiFi status (cmd 0x06)...')
    pkts = send_and_recv(ser, 0, 0x06, wait=2)
    for p in pkts:
        print(f'  {fmt_pkt(p)}')
    if not pkts:
        print('  No response.')


def cmd_version(ser):
    """Query firmware version."""
    print('Querying version (cmd 0x11)...')
    pkts = send_and_recv(ser, 0, 0x11, wait=2)
    for p in pkts:
        print(f'  {fmt_pkt(p)}')
    if not pkts:
        print('  No response.')


def cmd_init(ser):
    """Full MCU init: heartbeat + product info + working mode + provision."""
    print('Full MCU init sequence (90s)...')
    buf = bytearray()
    start = time.time()
    product_sent = False
    provision_sent = False

    while time.time() - start < 90:
        seq = int(time.time() - start) & 0xFF
        ser.write(make_pkt(seq, 0x00, b'\x01'))
        time.sleep(0.3)
        chunk = ser.read(2048)
        if chunk:
            buf.extend(chunk)
        pkts, buf = parse_pkts(buf)
        buf = bytearray(buf)
        for p in pkts:
            t = time.time() - start
            print(f'  [{t:4.0f}s] {fmt_pkt(p)}')

            if p['cmd'] == 0x01:
                ser.write(make_pkt(p['seq'], 0x01, PRODUCT_INFO))
                print(f'         >> Product info sent')
                product_sent = True
            elif p['cmd'] == 0x02:
                ser.write(make_pkt(p['seq'], 0x02, b'\x00'))
                print(f'         >> Working mode sent')
            elif p['cmd'] == 0x03 and not provision_sent:
                time.sleep(0.5)
                ser.write(make_pkt(0, 0x10))
                print(f'         >> Factory reset sent')
                time.sleep(1)
                ser.write(make_pkt(1, 0x04))
                print(f'         >> Provision mode sent')
                provision_sent = True

        time.sleep(0.2)

    print(f'Done. product_sent={product_sent} provision_sent={provision_sent}')


def cmd_monitor(ser):
    """Monitor all UART traffic indefinitely."""
    print('Monitoring UART (Ctrl+C to stop)...')
    buf = bytearray()
    try:
        while True:
            chunk = ser.read(2048)
            if chunk:
                buf.extend(chunk)
            pkts, buf = parse_pkts(buf)
            buf = bytearray(buf)
            for p in pkts:
                ts = time.strftime('%H:%M:%S')
                print(f'[{ts}] {fmt_pkt(p)}  raw={p["raw"].hex(" ")}')
            time.sleep(0.1)
    except KeyboardInterrupt:
        print('\nStopped.')


def main():
    parser = argparse.ArgumentParser(description='HeFi UART control for Dreo DR-HTF007S')
    parser.add_argument('port', help='Serial port (e.g. /dev/tty.usbserial-2120)')
    parser.add_argument('command', choices=['provision', 'reset', 'status', 'version', 'init', 'monitor'],
                        help='Command to execute')
    parser.add_argument('-b', '--baud', type=int, default=115200)
    args = parser.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=0.1)
    ser.reset_input_buffer()

    try:
        {'provision': cmd_provision,
         'reset': cmd_reset,
         'status': cmd_status,
         'version': cmd_version,
         'init': cmd_init,
         'monitor': cmd_monitor}[args.command](ser)
    finally:
        ser.close()


if __name__ == '__main__':
    main()
