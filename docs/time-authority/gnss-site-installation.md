---
id: roko-time-authority.gnss-site-installation
title: GNSS antenna and site installation
summary: Survey, antenna, cable, grounding, safety, interference, and active-lock requirements.
audience: [professional, agent]
tasks: [survey, install, protect]
status: draft-mainnet-policy
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Planning or installing the mandatory GNSS path.
previous: mainnet-hardware.md
next: hardware-deployment.md
---

# GNSS antenna and site installation

Mainnet requires active GNSS, not merely an attached antenna. Site design must
produce sustained satellite tracking, valid UTC time-of-day, and stable PPS.

## Survey and installation

- Obtain permission for roof, wall, window, or antenna-farm installation.
- Prefer wide sky view away from reflective walls, transmitters, high-current
  equipment, and RF interference.
- Confirm constellations/bands and antenna bias voltage before connection.
- Calculate coax and component loss across the exact bands and cable length.
- Use approved low-loss coax, connectors, splitters, DC blocks, and surge parts.
- Design grounding, bonding, weather sealing, drip loops, strain relief, labels,
  and a replaceable surge-protection boundary.
- Use qualified installers for rooftop and lightning work; follow local
  electrical, structural, fire, and occupational-safety codes.

Do not improvise antenna power injection or connect incompatible active
antennas. Never work on roofs or exposed conductors during unsafe weather.

## Resilience and security

Consider dual receivers/antennas with spatial separation, spare antenna/cable
assemblies, and documented switching. Monitor C/N0, satellites used,
constellation diversity, position/TOD validity, antenna open/short alarms,
jamming indicators, and position/time changes. Cross-check GNSS against
independent Stratum 1/2 and ROKO sources to detect gross TOD errors or spoofing.

Require stable tracking over a representative window, not a single fix. Record
satellites visible/used, constellations, signal levels, position validity,
antenna alarms, cable path, weather, and receiver mode. No active satellites is
a failure even when the card, PHC, or PPS device exists.

---

Pagenbar: [← Hardware selection](mainnet-hardware.md) · [Index](README.md) · [Next: Hardware deployment →](hardware-deployment.md)
