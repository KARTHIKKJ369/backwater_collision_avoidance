# LoRa Gateway Firmware

This folder is reserved for the LoRa to MQTT bridge implementation.

Planned responsibilities:

- Receive SX1278 LoRa packets from boat ESP32 nodes.
- Validate packet checksum and JSON structure.
- Publish telemetry to `boats/{id}/sensor`.
- Subscribe to `boats/{id}/alert` and `boats/{id}/status` for optional feedback devices.
