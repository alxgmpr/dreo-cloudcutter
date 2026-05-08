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

## MCU firmware update mechanism

The WiFi module acts as an OTA proxy for the MCU. The flow:

1. Cloud pushes OTA via AWS IoT shadow (`d_ota` attribute, `desired/sch` topic)
2. WiFi module downloads firmware from cloud OTA server (TLS)
3. WiFi module forwards firmware to MCU via Tuya UART commands `0x0E` (OTA start) / `0x0F` (OTA data)
4. Events reported back: `ota_firmware_update`, `ota_error` with MCU error codes

The download partition (`0x133000`–`0x1d2220`, ~636KB) contains a previous encrypted+compressed OTA image (RBL container at `0x131f9a`, version string `1018`). This is the WiFi module's own previous OTA — the MCU firmware would be downloaded and streamed directly to the MCU, not stored persistently on the WiFi flash.

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

### Cloud OTA parameters

```
firmware_url           ← download URL (from cloud shadow)
silent                 ← silent update flag  
check_model            ← model verification before flash
upgrade_only           ← upgrade-only flag (no downgrades?)
mcuFirmwareVersion     ← reported to cloud
mcuHardwareModel       ← reported to cloud
moduleFirmwareVersion  ← reported to cloud
moduleHardwareModel    ← reported to cloud
```

## Cloud OTA firmware download flow

The WiFi module receives OTA commands via AWS IoT shadow and downloads firmware from the Dreo cloud:

```
1. Cloud publishes to:  %s/things/%s/shadow/update/delta
   Also subscribes to:  %s/things/%s/shadow/update/accepted
   Schedule topic:       data/%s/desired/schedule
   Event topic:          event/%s/desired

2. Shadow delta contains JSON with:
   - firmware_type     ("module" or "mcu")
   - firmware_version  (target version string)
   - firmware_url      (HTTPS download URL)
   - silent            (silent update flag)
   - check_model       (verify model before flash)
   - upgrade_only      (prevent downgrades)

3. Module logs: "json_data:%s" then "URL:%s"
4. Connects to OTA server via TLS, downloads firmware
5. For module OTA: writes to download partition, reboots
6. For MCU OTA: streams to CMS80F7518 via Tuya UART (cmd 0x0E/0x0F)
7. Reports: {"event": [{"type":"ota_firmware_update","value":"%s_%s_%s"}]}
   On error: {"type":"ota_error","value":"mcu|%d|%d|%d|%d"}
```

Cloud endpoint: `https://iot.dreo-cloud.com/api/%s/health/mqtt-cluster/1.0.1.json`

### HTTP OTA handler (reversed from 0x067ab2)

The webserver HTTP handler at function `0x067ab2` dispatches:

```
GET /module  → serves HTML form (title="SOC", version="3.8.8"), calls OTA handler
GET /mcu     → calls sub_063554(), serves HTML form (title="MCU"), calls OTA handler
GET /ota     → serves HTML form, calls OTA handler

POST /module → sets ota_type="SOC", erases flash, streams upload to download partition
POST /mcu    → sets ota_type="MCU", erases flash, streams upload, forwards to MCU
POST /ota    → generic OTA handler

404          → "The path which is requested is not found!"
```

The HTML form served is:
```html
<form method="POST" enctype="multipart/form-data">
    <h3> %s OTA: %s</h3>
    <input type="file" name="firmware">
    <input type="submit" value="update">
</form>
```

Where `%s` is "SOC"/"MCU" and the firmware version.

## Debug UART log (TX2/RX2, 115200 8N1)

Key identifiers from boot log:
```
BK7231n_1.0.8                            ← bootloader version
SDK Rev: 3.0.46_20220921_d9dce354c70f    ← Beken SDK
BLE Rev: B5-3.0.46-P0
OSK Rev: F-3.0.28
Date: Oct 10 2025 13:38:45               ← firmware build date
firware ver:3.8.8                         ← application firmware version
chip id=7231c device id=0x20521028
ble_name: DREOtf07
ble mac:00-1c-c2-83-5b-e2
MAC address: 00:1c:c2:83:5b:e1
license.sn:1453300621256003585-e687f17eb2ef75aa:001:0000000000w
version:1-0-3                             ← HeFi protocol version
```

## Firmware strings of interest

```
dreo/hefi 1.0.3                          ← firmware stack identifier (HeFi = HeSung Firmware?)
DREOtf07                                 ← BLE device name / model
007+CMS89F7518/USA+3.0.6                 ← MCU product info (Tuya cmd 0x01 response)
https://iot.dreo-cloud.com/api/%s/health/mqtt-cluster  ← cloud endpoint
fan-device                               ← device class
/module, /mcu, /ota                      ← HTTP OTA endpoints
firware ver:3.8.8                        ← WiFi module firmware version
Date: Oct 10 2025 13:38:45               ← build date
```
