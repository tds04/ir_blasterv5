# IR Blaster — Home Assistant HACS Integration

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tds04&repository=ir_blaster&category=integration)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/tds04/ir_blaster)

> Local control for Tuya IR blasters (PID: zG1yTHAcRg5YvqyA) via Tasmota MQTT — no cloud required.

Local control integration for the RSH-Smart-IR V6 IR blaster board (sold under various brand names). Replaces Tuya cloud with full local control via Tasmota and MQTT.

The board uses a dedicated IR MCU for all transmission and reception, with a TYWE3S (ESP8266) WiFi module acting as a UART bridge. This integration talks to Tasmota running on the TYWE3S via MQTT, exposing study/learn mode and IR code transmission to Home Assistant.

**Reverse engineered via UART traffic analysis — no Tuya cloud, no app, no account required.**

## Supported Hardware

- Board: RSH-Smart-IR V6 (2018)
- WiFi module: TYWE3S (ESP8266, 1MB)
- IR MCU: Dedicated on-board controller
- UART: 9600 baud, Tuya MCU serial protocol
- Tuya Product ID: `zG1yTHAcRg5YvqyA`
- Tuya Product Code: `IRREMOTEWFBK`

## Requirements

- Home Assistant with MQTT integration configured
- Tasmota flashed to the device's WiFi module (TYWE3S)
- MQTT broker (e.g. Mosquitto)

## Tasmota Setup

Flash Tasmota lite to the TYWE3S module. In the Tasmota console:

```
Backlog Template {"NAME":"Tuya IR","GPIO":[0,0,0,0,0,0,0,0,0,0,0,0,0],"FLAG":0,"BASE":54}; Module 0
Baudrate 9600
SetOption66 1
Topic Irblaster
```

Configure MQTT in **Configuration → Configure MQTT** to point to your broker.

## Installation via HACS

1. In HACS → Integrations → Custom Repositories
2. Add `https://github.com/tds04/ir_blaster` as type **Integration**
3. Install **IR Blaster**
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → **IR Blaster**
6. Enter your device name and Tasmota MQTT topic

## Entities Created

| Entity | Type | Purpose |
|--------|------|---------|
| `sensor.ir_blaster_last_captured_code` | Sensor | Last IR code captured during study mode |
| `text.ir_blaster_code_name` | Text | Type a name here before pressing Learn |
| `text.ir_blaster_send_code` | Text | Send any IR code by hex or protocol string |
| `button.ir_blaster_learn` | Button | Start learning a new code |
| `button.ir_blaster_send_last_captured` | Button | Resend last captured code (test) |
| `button.ir_blaster_<n>` | Button | One per saved code — fires that IR code |
| `button.ir_blaster_delete_<n>` | Button | Deletes the corresponding saved code |

## Learning New Codes

All learning happens directly on the device card — no config menus needed.

1. Find the **Code Name** text field on the device card
2. Type a name for the button (e.g. `Fireplace On`, `TV Power`)
3. Press the **Learn** button
4. Point your remote at the IR blaster and press the button within 30 seconds
5. A notification appears confirming the code was captured — it shows the decoded protocol name if recognised (e.g. `nec:addr=0xDE,cmd=0xED`) or the raw hex if not
6. A new button appears on the device card — press it to fire that IR code

Repeat for each button you want to control. Codes are stored persistently and survive HA restarts.

## Testing

Use **Send Last Captured** to verify the full pipeline:
1. Press **Learn**, point remote, press button — sensor updates
2. Press **Send Last Captured** — IR fires

## Sending Codes via Automation

Write to the `text.ir_blaster_send_code` entity. The `Send Code` field accepts several formats:

### Raw hex (as captured from device)

The raw 80-byte blob returned by the device during learning:

```yaml
service: text.set_value
target:
  entity_id: text.ir_blaster_send_code
data:
  value: "B45A0B0B0B220B220B220B220B0B..."
```

### Protocol string (recommended for manual codes)

Human-readable format — no need to calculate raw hex by hand:

```yaml
service: text.set_value
target:
  entity_id: text.ir_blaster_send_code
data:
  value: "nec:addr=0xDE,cmd=0xED"
```

The notification shown after learning will tell you which format was identified. You can paste the protocol string directly into automations.

### Raw timing string

Explicit microsecond pulse/gap timings:

```yaml
service: text.set_value
target:
  entity_id: text.ir_blaster_send_code
data:
  value: "raw:9000,4500,560,560,560,1690,560,560,560,1690,..."
```

## Supported IR Protocols

The integration automatically identifies the protocol of a captured code and displays it in the learn notification. The same protocol strings can be used for sending.

| Protocol | Format | Parameters |
|----------|--------|------------|
| NEC (32-bit) | `nec:addr=0x..,cmd=0x..` | addr 0x00–0xFF, cmd 0x00–0xFF |
| NEC Extended | `nec-ext:addr=0x..,cmd=0x..` | addr 0x0000–0xFFFF, cmd 0x0000–0xFFFF |
| NEC 42-bit | `nec42:addr=0x..,cmd=0x..` | addr 0x0000–0x1FFF, cmd 0x00–0xFF |
| NEC 42-bit Ext | `nec42-ext:addr=0x..,cmd=0x..` | addr up to 0x3FFFFFF |
| RC5 / RC5X | `rc5:addr=0x..,cmd=0x..` | addr 0x00–0x1F, cmd 0x00–0x7F |
| RC6 | `rc6:addr=0x..,cmd=0x..` | addr 0x00–0xFF, cmd 0x00–0xFF |
| Samsung 32-bit | `samsung32:addr=0x..,cmd=0x..` | addr 0x00–0xFF, cmd 0x00–0xFF |
| Sony SIRC 12-bit | `sirc:addr=0x..,cmd=0x..` | addr 0x00–0x1F, cmd 0x00–0x7F |
| Sony SIRC 15-bit | `sirc15:addr=0x..,cmd=0x..` | addr 0x00–0xFF, cmd 0x00–0x7F |
| Sony SIRC 20-bit | `sirc20:addr=0x..,cmd=0x..` | addr 0x0000–0x1FFF, cmd 0x00–0x7F |
| Kaseikyo (Panasonic) | `kaseikyo:vendor_id=0x..,genre1=0x..,genre2=0x..,data=0x..,id=0x..` | |
| RCA | `rca:addr=0x..,cmd=0x..` | addr 0x00–0x0F, cmd 0x00–0xFF |
| Pioneer | `pioneer:addr=0x..,cmd=0x..` | addr 0x00–0xFF, cmd 0x00–0xFF |
| Air Conditioner | `ac:addr=0x..,cmd=0x..` | addr 0x00–0xFF, cmd 0x0000–0xFFFF |
| Raw timings | `raw:t1,t2,t3,...` | Microsecond pulse/gap values |

RC5 and RC6 automatically toggle the toggle bit on each send to signal distinct button presses, which is required by some devices.

## Technical Details

This device uses a dedicated IR MCU that handles all IR transmission and reception. The TYWE3S WiFi module communicates with the IR MCU over UART at 9600 baud using the Tuya serial protocol (55 AA framing).

### IR Code Format

The 80-byte raw code blob stored internally is a sequence of up to 80 uint8 timing values, where each unit represents 50 microseconds. Values alternate between pulse and gap durations starting with the leading pulse. Trailing zeros are padding.

For a standard NEC code this looks like:

```
0xB4 = 180 × 50µs = 9000µs  (NEC leading pulse)
0x5A =  90 × 50µs = 4500µs  (NEC leading gap)
0x0B =  11 × 50µs =  550µs  (data pulse)
0x22 =  34 × 50µs = 1700µs  (data gap = '1' bit)
...
```

### Key Packet Sequences

| Action | Packet |
|--------|--------|
| Study On | `55AA000600050104000101 11` |
| Study Off | `55AA000600050104000102 12` |
| Send IR (DP7) | `55AA000600540700005 0 [80 bytes] [checksum]` |

IR codes are reported back from the MCU on DP2 or DP7 via the `TuyaReceived` MQTT message from Tasmota.

## Credits

Reverse engineered from IRREMOTEWFBK using TuyaMCU Explorer/Analyzer and Waveshare USB serial adapter. Protocol documented through extensive UART traffic analysis.

IR protocol encode/decode library adapted from [localtuya_rc](https://github.com/ClusterM/localtuya_rc) by Alexey Cluster (MIT/GPL-3.0).
