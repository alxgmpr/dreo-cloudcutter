#!/usr/bin/env python3
"""OTA upload for Dreo DREOtf07. Keeps UART heartbeat alive while uploading firmware."""

import serial
import threading
import time
import sys
import subprocess

def make_pkt(seq, cmd, data=b''):
    p = bytes([0x55, 0xAA, 0x00, seq & 0xFF, cmd, 0x00, len(data) >> 8, len(data) & 0xFF]) + data
    return p + bytes([sum(p) & 0xFF])


def heartbeat_loop(ser, stop_event):
    seq = 0
    while not stop_event.is_set():
        try:
            ser.write(make_pkt(seq, 0x00, b'\x01'))
            ser.read(1024)
        except serial.SerialException:
            break
        seq = (seq + 1) & 0xFF
        time.sleep(0.5)


def main():
    if len(sys.argv) < 3:
        print(f'Usage: {sys.argv[0]} <serial_port> <firmware.rbl>')
        sys.exit(1)

    port = sys.argv[1]
    firmware = sys.argv[2]

    ser = serial.Serial(port, 115200, timeout=0.3)
    ser.reset_input_buffer()

    # Step 1: Check module is alive
    print('[1] Checking module...', flush=True)
    alive = False
    for i in range(20):
        ser.write(make_pkt(i, 0x00, b'\x01'))
        time.sleep(0.5)
        r = ser.read(1024)
        if r:
            print(f'    Module alive', flush=True)
            alive = True
            break
    if not alive:
        print('    NOT RESPONDING. CEN reset or power cycle needed.', flush=True)
        ser.close()
        sys.exit(1)

    # Step 2: Factory reset
    print('[2] Factory reset...', flush=True)
    ser.write(make_pkt(0, 0x10))
    time.sleep(2)
    r = ser.read(2048)
    if r:
        print(f'    OK', flush=True)

    # Step 3: Provision mode
    print('[3] Provision mode...', flush=True)
    ser.write(make_pkt(1, 0x04))
    time.sleep(2)
    r = ser.read(2048)
    if r:
        print(f'    OK', flush=True)

    # Step 4: Start heartbeat background thread
    print('[4] Starting heartbeat thread...', flush=True)
    stop = threading.Event()
    hb_thread = threading.Thread(target=heartbeat_loop, args=(ser, stop), daemon=True)
    hb_thread.start()

    # Step 5: Wait for user to connect to AP
    print('[5] Connect to the Dreo AP now.', flush=True)
    print('    Waiting for 192.168.0.1 to be reachable...', flush=True)
    for i in range(60):
        result = subprocess.run(['ping', '-c', '1', '-W', '2', '192.168.0.1'],
                                capture_output=True, timeout=5)
        if result.returncode == 0:
            print(f'    AP reachable!', flush=True)
            break
        time.sleep(2)
    else:
        print('    Timeout waiting for AP.', flush=True)
        stop.set()
        ser.close()
        sys.exit(1)

    # Step 6: Verify form
    print('[6] Verifying OTA form...', flush=True)
    result = subprocess.run(['curl', '-s', '--max-time', '5', 'http://192.168.0.1/module'],
                            capture_output=True, text=True, timeout=10)
    if 'OTA' not in result.stdout:
        print(f'    Form not found: {result.stdout[:100]}', flush=True)
        stop.set()
        ser.close()
        sys.exit(1)
    print(f'    Form OK', flush=True)

    # Step 7: Stop heartbeat before upload — UART traffic interferes with OTA
    print('[7] Stopping heartbeat...', flush=True)
    stop.set()
    hb_thread.join(timeout=2)
    ser.close()
    time.sleep(0.5)

    # Step 8: Upload
    print(f'[8] Uploading {firmware}...', flush=True)
    result = subprocess.run(
        ['curl', '-s', '-w', '%{http_code}', '--max-time', '120',
         '-F', f'firmware=@{firmware}', 'http://192.168.0.1/module'],
        capture_output=True, text=True, timeout=180)

    http_code = result.stdout[-3:] if len(result.stdout) >= 3 else '?'
    body = result.stdout[:-3] if len(result.stdout) >= 3 else result.stdout
    print(f'    HTTP {http_code}: {body.strip()}', flush=True)

    if 'download error' in body:
        print('\nFIRMWARE REJECTED by validation.', flush=True)
        sys.exit(1)
    elif http_code == '200' or result.returncode == 28:
        print('\nUpload sent. Check if device boots new firmware.', flush=True)
    else:
        print(f'\nUnexpected result.', flush=True)


if __name__ == '__main__':
    main()
