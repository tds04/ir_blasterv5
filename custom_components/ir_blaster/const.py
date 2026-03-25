"""Constants for IR Blaster integration."""

DOMAIN = "ir_blaster"

CONF_TOPIC = "mqtt_topic"
CONF_DEVICE_NAME = "device_name"

# MQTT topics (Tasmota convention)
TOPIC_SEND = "cmnd/{topic}/SerialSend5"
TOPIC_RESULT = "tele/{topic}/RESULT"

# Tuya MCU packets — sent as separate SerialSend5 calls
# Packet 1: DP1 enum=0 (send_ir trigger), cmd 06
PKT_SEND_TRIGGER = "55AA000600050100000100 0C"
# Packet 2 prefix: DP7 raw header (80 byte payload = 0x50), cmd 06
# Full packet: PKT_SEND_CODE_HDR + 80_bytes_hex + checksum
PKT_SEND_CODE_HDR = "55AA0006005407000050"

# Study on/off
PKT_STUDY_ON  = "55AA000600050104000101 11"
PKT_STUDY_OFF = "55AA000600050104000102 12"

# DP keys in TuyaReceived
DP_IR_CODE_7 = "DpType0Id7"
DP_IR_CODE_2 = "DpType0Id2"

DEFAULT_TOPIC = "Irblaster"
LEARN_TIMEOUT = 30  # seconds

# Storage
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = "ir_blaster_codes_"

# Learning session states
STATE_IDLE      = "idle"
STATE_ARMED     = "armed"
STATE_RECEIVED  = "received"
STATE_TIMEOUT   = "timeout"
STATE_CANCELLED = "cancelled"

DEFAULT_CODE_NAME_PLACEHOLDER = "Enter code name..."
