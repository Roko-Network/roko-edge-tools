---
id: roko-time-authority.hardware-deployment
title: Physical clock deployment and configuration
summary: Installation sequence for appliances and PCIe cards, including GNSS, PHC, PPS, TOD, and clock ownership.
audience: [professional, agent]
tasks: [install, configure, integrate]
status: draft-mainnet-policy
version: 1.0.0
last_reviewed: 2026-08-01
read_when: Installing approved hardware on a target mainnet site.
previous: gnss-site-installation.md
next: hardware-acceptance.md
---

# Physical clock deployment and configuration

Use vendor instructions for the exact revision. This sequence is the ROKO
integration envelope and does not replace electrical or vendor manuals.

1. Record pre-change clock, kernel, firmware, PCIe, NIC, network, and service
   state. Keep the node non-authoring.
2. Power down for PCIe installation and follow ESD, power, airflow, retention,
   and vendor handling requirements.
3. Install and weatherproof the approved GNSS antenna path.
4. Boot and confirm the exact device, firmware, driver, PHC, PPS, GNSS
   interface, and interface-to-PHC mapping.
5. Confirm live satellites and valid GNSS position/time-of-day.
6. Confirm PPS and associate it with the correct GNSS TOD source.
7. Configure oscillator/servo and allow documented warm-up/learning time.
8. Configure exactly one steering chain from GNSS/PHC to system clock.
9. Cross-check UTC against `ntp01.roko.network` and a nearby Stratum 1/2 source.
10. Install Timebeat/PTP Squared and ROKO only after hardware acceptance.

Linux exposes supported clocks under `/dev/ptp*` and `/sys/class/ptp`, with
PPS commonly under `/dev/pps*`. Device numbers are not stable identifiers—map
by PCI address, interface, driver, and metadata. See the
[Linux PHC documentation](https://docs.kernel.org/next/driver-api/ptp.html) and
[OCP Time Card guide](https://github.com/opencomputeproject/Time-Appliance-Project/wiki/Time-Card-installation-and-usage).

## Critical TOD/PPS rule

PPS supplies phase within a second; it does not prove which UTC second is
correct. Clean PPS can coexist with a whole-second error when GNSS TOD is
missing or linked incorrectly. Require both live PPS and valid GNSS TOD, then
compare them with independent UTC sources.

Appliances require isolated management/service networks and deliberate
grandmaster behavior. PCIe cards require verified BIOS/IOMMU, driver/firmware,
IRQ/CPU, thermal, and NIC timestamping behavior. Never flash firmware without
exact revision matching, checksums, backup, and rollback.

---

Pagenbar: [← GNSS site installation](gnss-site-installation.md) · [Index](README.md) · [Next: Hardware acceptance →](hardware-acceptance.md)
