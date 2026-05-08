# DREOtf07 — CMS80F7518 + WZ07-W (BL2028N)

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

Extracted from firmware attribute table at flash offset `0x0ffbc0` and verified against live UART capture.

| DP ID | Name | Tuya Type | Description |
|-------|------|-----------|-------------|
| 1 | poweron | Bool | Fan power on/off |
| 2 | ledalwayson | Bool | LED always on |
| 3 | windtype | Enum | Fan mode (normal/natural/sleep/auto) |
| 4 | windlevel | Enum | Fan speed |
| 5 | voiceon | Bool | Beeper on/off |
| 6 | timeron | Value | Timer on duration |
| 7 | timeroff | Value | Timer off duration |
| 8 | shakehorizon | Bool | Horizontal oscillation on/off |
| 9 | *(unknown)* | Enum | — |
| 11 (0x0b) | temperature | Value | Ambient temperature (°F) |
| 12 (0x0c) | *(unknown)* | Enum | — |
| 18 (0x12) | tempunit | Int | Temperature unit |
| 32 (0x20) | scheon | Enum | Schedule on |
| 33 (0x21) | connected | Enum | Cloud connected status |
| 34 (0x22) | mcuon | Enum | MCU on |

Additional metadata attributes (not DPs): `module_hardware_model`, `module_hardware_mac`, `mcu_hardware_model`, `mcu_firmware_version`, `wifi_rssi`, `wifi_ssid`, `network_latency`, `timeron.ts`, `timeroff.ts`, `d_ota`, `scheid`.

## CMS80F7518 MCU

- 8051 core, 48MHz, 32KB flash, 2KB RAM
- Programmed via proprietary 2-wire interface (DSDA/DSCK), NOT UART or SWD
- Requires CMS-ICE8 PRO programmer (~$30 on AliExpress)
- Flash likely read-protected in production
- No open-source tooling exists

## WiFi module (WZ07-W / MBL01)

Same BL2028N chip as the DR-HTF004S. Dump procedure identical to main README: `ltchiptool flash read` via RX1/TX1, reset via CEN.

FCC ID: [2A3SYMBL01](https://fcc.report/FCC-ID/2A3SYMBL01)

## Firmware strings of interest

```
dreo/hefi 1.0.3                          ← firmware stack identifier
DREOtf07                                 ← BLE device name / model
007+CMS89F7518/USA+3.0.6                 ← MCU product info string
https://iot.dreo-cloud.com/api/%s/health/mqtt-cluster  ← cloud endpoint
fan-device                               ← device class
```
