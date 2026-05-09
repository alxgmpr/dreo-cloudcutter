# DREOtf07 — CMS80F7518 + WZ07-W (BL2028N)

FCC ID: [2BPBC-HTF009](https://fcc.report/FCC-ID/2BPBC-HTF009)

Findings for a Dreo tower fan using a **different MCU and UART protocol** than the DR-HTF004S documented in the main README.

## Key differences from DR-HTF004S

| | DR-HTF004S (main README) | DREOtf07 (this doc) |
|---|---|---|
| MCU | SH79F9463P (SinoWealth 8051) | CMS80F7518 (CMS 8051, 48MHz, 32KB flash) |
| WiFi module | PAI-053 / BL2028N | WZ07-W (MBL01) / BL2028N |
| UART protocol | Custom `AA xx FA` framing | **Standard Tuya MCU protocol** (`55 AA`) |
| Checksum | Custom (negative sum - 2×len) mod 256 | Tuya standard: sum of all bytes mod 256 |
| Datapoints | Custom byte map (fixed offsets) | Tuya DP format (id/type/len/value TLVs) |
| Firmware stack | Unknown | `dreo/hefi 1.0.3` |
| Cloud | AWS IoT | AWS IoT via `iot.dreo-cloud.com` |
| BLE name | Dreo... | DREOtf07 |

The CMS80F7518 variant uses the standard Tuya MCU serial protocol, meaning existing TuyaMCU tooling (Tasmota TuyaMCU, ESPHome tuya component) may work directly without custom UART lambdas.

## UART protocol

Standard Tuya MCU protocol at **115200 8N1**. Frame format:

```
55 AA VV CC LLLL DD...DD SS
│  │  │  │  │    │       └─ Checksum: sum(all bytes) & 0xFF
│  │  │  │  │    └──────── Data (LLLL bytes)
│  │  │  │  └───────────── Data length (big-endian u16)
│  │  │  └──────────────── Command type
│  │  └─────────────────── Version (0x00)
└──┘────────────────────── Header
```

Reference: [Tuya MCU Protocol](https://developer.tuya.com/en/docs/iot/mcu-protocol?id=K9hrdpyujeotg)

## Boot capture

Raw hex from power-on (MCU → WiFi):

```
55 aa 00 06 00 00 00 01 01 07 00 fe
55 aa 00 00 07 00 00 40
  01 01 00 01 00     ← DP 1:  Bool  = true   (poweron)
  02 01 00 01 00     ← DP 2:  Bool  = false  (ledalwayson)
  03 04 00 01 01     ← DP 3:  Enum  = 1      (windtype)
  04 04 00 01 04     ← DP 4:  Enum  = 4      (windlevel)
  05 01 00 01 01     ← DP 5:  Bool  = true   (voiceon)
  06 02 00 04 00000000  ← DP 6:  Value = 0   (timeron)
  07 02 00 04 00000000  ← DP 7:  Value = 0   (timeroff)
  08 01 00 01 00     ← DP 8:  Bool  = false  (shakehorizon)
  09 04 00 01 00     ← DP 9:  Enum  = 0      (unknown)
  0b 02 00 04 0000004f ← DP 11: Value = 79   (temperature, °F)
  0c 04 00 01 01     ← DP 12: Enum  = 1      (unknown)
55 aa 00 00 01 00 00 18
  30 30 37 2b 43 4d 53 38 39 46 37 35 31 38 2f 55 53 41 2b 33 2e 30 2e 36
  → ASCII: "007+CMS89F7518/USA+3.0.6"  (product info response)
```

## Datapoint map

Extracted from firmware CBOR attribute table at flash offset `0x0f0b12` and verified against live UART capture.

| DP ID | Name | Tuya Type | R/W | Description |
|-------|------|-----------|-----|-------------|
| 1 | poweron | Bool (0x01) | rw | Fan power on/off |
| 2 | ledalwayson | Bool (0x01) | rw | LED always on (display auto-off when false) |
| 3 | windtype | Enum (0x04) | rw | Fan mode: 1=Normal, 2=Natural, 3=Sleep, 4=Auto |
| 4 | windlevel | Enum (0x04) | rw | Fan speed: 1-4 (CMS80F7518), 1-8 (SC95F8613B) |
| 5 | voiceon | Bool (0x01) | rw | Beeper on/off |
| 6 | timeron | Value (0x02) | rw | Turn-on timer countdown in minutes (set when fan is off, 0-480) |
| 7 | timeroff | Value (0x02) | rw | Turn-off timer countdown in minutes (set when fan is on, 0-480) |
| 8 | shakehorizon | Bool (0x01) | rw | Horizontal oscillation on/off |
| 9 | wrong | Enum (0x04) | ro | Fault indicator: 0=OK, 1=E1 (back cover), 2=EU (sensor failure) |
| 11 (0x0b) | temperature | Value (0x02) | ro | Ambient temperature (°F when tempunit=1) |
| 12 (0x0c) | tempunit | Enum (0x04) | ro | Temperature unit: 0=°C, 1=°F |
| 18 (0x12) | scheon | Bool (0x01) | wo | Schedule execution trigger (sending 1 powers on the fan; not reported in DP status) |

Metadata attributes (negative CBOR `c` values, NOT Tuya DPs — handled internally by WiFi module):
`connected`, `mcuon`, `module_hardware_model`, `module_hardware_mac`, `module_firmware_version`.

### Status LEDs (known issue)

The display panel has 4 status LEDs: WiFi, unknown, oscillate, schedule. The oscillate LED is controlled by DP8. The WiFi LED is driven by the MCU's internal handshake state counter (XDATA 0x0112) and cannot be controlled via WiFi status cmd 0x03 or any known DP. The stock firmware's cloud connection flow likely sets the counter to the right value through a sequence we haven't replicated. WiFi LED control is an open issue.

### Timer button behavior

The physical timer button cycles through 0→1→2→3→4→5→6→7→8→0 hours. Pressing sets DP6 (timeron) when the fan is OFF, or DP7 (timeroff) when ON. Values are in minutes (e.g., 3h = 180). The MCU requests time sync (cmd 0x0E) when the timer is activated. Timer counts down by 1 per minute.

## CMS80F7518 MCU

- 8051 core, 48MHz, 32KB flash, 2KB RAM
- Programmed via proprietary 2-wire interface (DSDA/DSCK), NOT UART or SWD
- Requires CMS-ICE8 PRO programmer (~$30 on AliExpress)
- Flash likely read-protected in production
- No open-source tooling exists

## WiFi module (WZ07-W / MBL01)

Same BL2028N chip as the DR-HTF004S. Dump procedure identical to main README: `ltchiptool flash read` via RX1/TX1, reset via CEN.

WiFi module FCC ID: [2A3SYMBL01](https://fcc.report/FCC-ID/2A3SYMBL01)

## MCU firmware update mechanism

The WiFi module acts as an OTA proxy for the MCU. MCU firmware has **never been published for OTA** through the Dreo cloud API — it is factory-only via CMS-ICE8 programmer. The WiFi module firmware (3.2.6) is available but the device shipped with a newer factory build (3.8.8).

### OTA file format (OTAU)

The `/mcu` HTTP endpoint validates uploads against this 128-byte header:

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 4 | Magic: `OTAU` (0x4F544155) |
| 0x04 | 4 | Product ID High (big-endian) |
| 0x08 | 8 | Product ID Low (big-endian) |
| 0x10 | 4 | Firmware Size (big-endian) |
| 0x14 | 5 | Reserved |
| 0x19 | 3 | Target Version (major.minor.patch) |
| 0x1C | 1 | Reserved |
| 0x1D | 3 | Min Upgrade Version (major.minor.patch) |
| 0x20 | 16 | MD5 Hash |
| 0x30 | 78 | Reserved/Padding |
| 0x7E | 2 | CRC-16/MODBUS (poly 0xA001, init 0xFFFF) over bytes 0x00-0x7D |

Validation order: length >= 128, magic == `OTAU`, CRC-16 check, product ID match, version check, min version check.

### UART OTA transfer protocol (WiFi → MCU)

After the WiFi module validates and stores the firmware, it forwards to the MCU via a modified Tuya protocol. The MCU drives the transfer (pull model).

UART frame format:
```
55 AA 00 <seq> <cmd> 00 <len_hi> <len_lo> <data...> <checksum>
```

| Cmd | Direction | Purpose | Payload |
|-----|-----------|---------|---------|
| 0x0A | WiFi→MCU | OTA Start | 4 bytes: firmware size (big-endian) |
| 0x0B | MCU→WiFi / WiFi→MCU | OTA Data request/response | Fixed 128-byte chunks |
| 0x0C | WiFi→MCU | OTA End | 0 bytes |
| 0x0F | WiFi→MCU | OTA Result | 1 byte: 0x02=success, 0x03=fail |
| 0x14 | Both | OTA Notify (subcommand) | Variable, CRC-8 protected (poly 0x07) |

Chunk size is fixed at **128 bytes (0x80)**. The MCU requests each chunk (cmd 0x0B), WiFi reads from flash and responds. Transfer runs in a dedicated RTOS task (`urgent_task`, priority 8).

The download partition (`0x133000`–`0x1d2220`, ~636KB) contains a previous encrypted WiFi module OTA image (RBL container). MCU firmware is streamed directly and not stored persistently on WiFi flash.

### Web server endpoints (differs from DR-HTF004S)

The DREOtf07 firmware has only three HTTP OTA paths (vs six+ on the DR-HTF004S):

| Endpoint | Description |
|----------|-------------|
| `/module` | WiFi module OTA upload |
| `/mcu` | MCU firmware OTA upload |
| `/ota` | Generic OTA endpoint |

Notably missing vs DR-HTF004S: `/wifilist`, `/appinfoset`, `/wifiinfoset`, `/devinfoget`, `/otaset`, `/otaLocalUp`, `/model.html`. This firmware uses the HeFi stack rather than the raw Beken webserver.

The `/mcu` endpoint is significant — it may allow uploading CMS80F7518 firmware via HTTP, bypassing the need for the proprietary CMS-ICE8 programmer. This needs testing.

### OTA state machine events

```
ota_start → ota_sslerr | transport → downend → file_size →
partition_info_write → partition_info_read → (complete)
```

Error reporting: `{"type":"ota_error","value":"mcu|%d|%d|%d|%d"}`

## Cloud API and firmware availability

Cloud API authentication, credentials, and OTA delivery flow are documented separately in the top-level security research workspace (see `extracted_creds/` and `cloud_api.md` in the parent repo).

Key facts for cloudcutting:
- Cloud OTA only has module firmware up to **3.2.6**. Our device shipped with **3.8.8** (factory-only, never published for OTA).
- MCU firmware (3.0.6) has **never been published for OTA** — factory-only via CMS-ICE8 programmer.
- `moduleHardwareModel` must be `HeFi` in firmware check requests.
