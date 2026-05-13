# Dreo Cloudcutter

Replace cloud-dependent firmware on Dreo tower fans with local [ESPHome](https://esphome.io/) control via [Home Assistant](https://www.home-assistant.io/).

> Forked from [ouaibe/dreo-cloudcutter](https://github.com/ouaibe/dreo-cloudcutter) (Apache 2.0). Original work by [@ouaibe](https://github.com/ouaibe) with help from [Gabriel Tremblay](https://github.com/gabtremblay) and [kuba2k2](https://github.com/kuba2k2) ([LibreTiny](https://docs.libretiny.eu/)). This fork focuses on the **DR-HTF007S**.

## Disclaimer

Educational purposes only. You will likely brick your device at some point — be prepared to connect via UART. See [LICENSE](LICENSE).

## Supported models

| | DR-HTF007S | DR-HTF004S |
|---|---|---|
| MCU | CMS80F7518 (8051, 48MHz, 32KB) | SH79F9463P (SinoWealth 8051) |
| WiFi module | WZ07-W (BL2028N) | PAI-053 (BL2028N) |
| UART protocol | Standard Tuya MCU (`55 AA`) | Custom Dreo (`AA xx FA`) |
| Checksum | `sum(all bytes) & 0xFF` | `(len - sum - 2*len) % 256` |
| Datapoints | Tuya DP TLVs | Fixed byte offsets |
| Firmware stack | `dreo/hefi 1.0.3` | Unknown |
| OTA endpoint | `/module` | `/model.html` |
| ESPHome config | [`DR-HTF007S.yaml`](esphome/DR-HTF007S.yaml) | [`Dreo_DR-HTF004S.yaml`](esphome/Dreo_DR-HTF004S.yaml) |

Full protocol docs: [docs/DR-HTF007S.md](docs/DR-HTF007S.md)

## Hardware

Both models use the BL2028N (BK7231M clone) WiFi chip. Key parameters:

| Parameter | Value |
|-----------|-------|
| Board | `generic-bk7231n-qfn32-tuya` |
| OTA Key | `0123456789ABCDEF0123456789ABCDEF` |
| OTA IV | `0123456789ABCDEF` |
| Download partition | `0x132000+0xAE000` |
| Calibration partition | `0x1E0000+0x1000` |
| App base address | `0x10000` |

UART: 9600 baud (DR-HTF004S MCU), 115200 baud (DR-HTF007S MCU / debug console on TX2/RX2). Use an FTDI232 at 3.3V.

## Flashing ESPHome

### Prerequisites

- [ESPHome](https://esphome.io/) installed (standalone or HA add-on)
- [LibreTiny](https://docs.libretiny.eu/docs/projects/esphome/) platform support

### Build

```bash
# Copy and edit secrets
cp esphome/secrets.yaml.example esphome/secrets.yaml

# Build the OTA image
esphome compile esphome/DR-HTF007S.yaml
```

The `.rbl` file will be at `.esphome/build/<name>/.pioenvs/<name>/image_bk7231n_app.ota.rbl`. It should start with `RBL` in a hex editor and contain no readable text (it's encrypted).

### Upload (DR-HTF007S)

1. Put the fan in pairing mode (factory reset or hold oscillation button)
2. Connect to the Dreo AP (`192.168.0.1`)
3. Upload the `.rbl` to `http://192.168.0.1/module`

Or use the included upload tool which keeps the UART heartbeat alive during OTA:

```bash
uv pip install -r tools/requirements.txt
uv run tools/ota_upload.py /dev/tty.usbserial-XXXX firmware.rbl
```

### Upload (DR-HTF004S)

1. Put the fan in pairing mode (hold oscillation button 5s)
2. Connect to the Dreo AP
3. Navigate to `http://192.168.0.1/model.html` and upload the `.rbl`

### Subsequent OTA

Once ESPHome is running, update over the network:

```bash
esphome upload esphome/DR-HTF007S.yaml --device <fan-ip>
```

## Tools

| Script | Purpose |
|--------|---------|
| [`hefi_uart.py`](tools/hefi_uart.py) | UART control: provision, factory reset, monitor, init sequence |
| [`ota_upload.py`](tools/ota_upload.py) | OTA upload with UART heartbeat keepalive |
| [`otau_wrap.py`](tools/otau_wrap.py) | Wrap an RBL in an OTAU container (for MCU OTA via `/mcu`) |

```bash
uv pip install -r tools/requirements.txt

# Monitor UART traffic
uv run tools/hefi_uart.py /dev/tty.usbserial-XXXX monitor

# Factory reset + enter AP mode
uv run tools/hefi_uart.py /dev/tty.usbserial-XXXX reset
```

## Firmware dumping

If you need to dump or restore the original firmware:

```bash
# Dump via ltchiptool (connect FTDI to RX1/TX1, ground CEN to enter flash mode)
ltchiptool flash read bk72xx dump.bin

# Remove CRC for analysis in Ghidra
ltchiptool soc bkpackager uncrc dump.bin dump_decrc.bin
```

Ghidra settings: ARM v5TE, little-endian, base address `0x10000`, skip first `0x11000` bytes (bootloader).

## Project structure

```
esphome/          ESPHome YAML configs + secrets
docs/             Protocol documentation
tools/            Python utilities (requires pyserial)
dumps/            Firmware dumps
images/           Documentation images
```

## License

Apache 2.0 — see [LICENSE](LICENSE).
