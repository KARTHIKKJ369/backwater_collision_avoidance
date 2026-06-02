# ESP32 Firmware

This folder is reserved for the sensor-node firmware once hardware is available.

Planned responsibilities:

- Read GPS, IMU, camera-derived obstacle status, and boat status.
- Serialize telemetry as JSON.
- Send packets over LoRa SX1278 to the gateway.
- Mirror the simulator payload:

```json
{
  "boat_id": "B01",
  "timestamp": 0,
  "lat": 9.591,
  "lon": 76.522,
  "speed": 4.2,
  "heading": 65,
  "obstacle": 0
}
```
