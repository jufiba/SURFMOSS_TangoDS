# TempSensorDS18B20

Room / rack temperature from a **Dallas DS18B20** 1-wire sensor on a Raspberry
Pi. The kernel does the 1-wire bit-banging; this server just reads the value
through `w1thermsensor`.

Two instances: `TempSensorDS18B20/1` → `mossbauer/temperature/roomtemperature`
on **pi-rackmossbauer**, `TempSensorDS18B20/2` → `leem/safety/roomtemperature`
on **pi-uleem**.

## Pi setup (once per machine)

The pin is driven by the kernel `w1-gpio` overlay, not by this server:

- `/etc/modules`: `w1_gpio`, `w1_therm`
- firmware config (`config.txt`): `dtoverlay=w1-gpio,gpiopin=4`
- package: `python3-w1thermsensor`

The sensor then appears under `/sys/bus/w1/devices/28-*`.

## Interface

- Property `GPIOPin` (default `4`) — **informational only**, it records which
  pin the overlay uses; the server does not touch GPIO.
- Attribute `Temperature` (double, °C). Served from a background poll every
  5 s. While no sensor is present the last value is returned with **INVALID**
  quality rather than passed off as fresh.

## Behaviour

The 1-wire bus is noisy — a slave can drop out of `/sys/bus/w1/devices` and
reappear a few searches later. The poll thread retries from scratch on every
failure and only goes `FAULT` after three in a row, so a brief dropout does
not freeze the reading or take the server down. An exception in `init_device`
(no sensor at start-up) also leaves the server up in `FAULT`; the thread
recovers on its own when the sensor comes back.

## Install

In `pyproject.toml`. Needs `w1thermsensor` and the Pi setup above.
