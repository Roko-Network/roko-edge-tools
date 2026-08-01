---
id: roko-time-authority.mainnet-hardware
title: Mainnet physical clock selection
summary: Mandatory capabilities, deployment classes, oscillator choices, and procurement evidence.
audience: [professional, agent]
tasks: [select, procure, design]
status: draft-mainnet-policy
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Selecting physical timing hardware for a mainnet validator.
previous: professional.md
next: gnss-site-installation.md
---

# Mainnet physical clock selection

Every mainnet validator must have a physical hardware clock with directly
connected, active GNSS. Receiving PTP or NTP from another site, detecting a
PHC, or running an oscillator in free holdover does not satisfy this requirement.

## Mandatory capabilities

- Multi-constellation GNSS with active satellite tracking and UTC time-of-day.
- Hardware 1 PPS tied to the same GNSS solution.
- OCXO or better disciplined oscillator and documented holdover behavior.
- Linux PHC/PPS support or a supported appliance management interface.
- Telemetry for GNSS, PPS, oscillator/servo, TOD, offset, alarms, and holdover.
- Antenna-fault, GNSS-loss, spoof/jam, PPS-loss, and holdover alarms.
- Supported firmware, reproducible configuration, and a safe distribution path.

Prefer multi-band GPS/Galileo and hardware timestamping. Verify receiver,
antenna bias voltage, connector, kernel, driver, firmware, and Timebeat version
as one compatibility set before purchase.

## Deployment classes

| Class | Appropriate use | Trade-offs |
| --- | --- | --- |
| Integrated PCIe time card | Validator server with a suitable slot and antenna route | Low internal latency; operator owns host/driver/firmware integration |
| Dedicated timing appliance | Professional rack/site serving protected consumers | Better isolation and redundancy; higher cost and network-design burden |
| Open OCP Time Card build | Advanced teams requiring open integration | Auditable and flexible; requires strong kernel, FPGA, GNSS, and lifecycle skills |

Reference families include Timebeat Open TimeCard/Open TimeCard Mini and Open
Time Appliance products, plus OCP Time Appliances Project-compatible cards.
Product names are examples, not automatic approval. Validate the exact SKU and
support lifecycle against the current [Timebeat hardware catalog](https://timebeat.app/)
and [OCP Time Appliances Project](https://www.opencompute.org/wiki/Time_Appliances_Project).

## Oscillator and procurement

OCXO is the minimum normal mainnet class. DOCXO can improve environmental
stability. Rubidium is appropriate when extended holdover justifies its cost,
warm-up, power, aging, and maintenance. Verify holdover under actual site
temperature, airflow, power, and outage duration; holdover never replaces the
active-GNSS requirement.

Record exact SKU/revision, GNSS module, oscillator, antenna, cable type/length,
surge protection, supported kernel/driver, firmware, support, calibration,
spares, checksum sources, and acceptance owner.

---

Pagenbar: [← Professional design](professional.md) · [Index](README.md) · [Next: GNSS site installation →](gnss-site-installation.md)
