# ROKO edge operator notes

[Edge guide](https://nodes.roko.network/edge/) ·
[ROKO Time](https://time.roko.network/) ·
[Back to tools](../README.md)

## Recommended operating model

1. Keep RPC local by default.
2. Use `ntp01.roko.network` as one NTP source, not the only source.
3. Serve LAN time only to private subnets.
4. Do not expose Chrony command controls to the network.
5. Add PTP² observer mode only after the node is synced and Chrony is healthy.

## ROKO PTP² boundary

ROKO PTP² is carried by the ROKO libp2p protocol `/roko/timesync/1`.
It is not IEEE 1588 PTP and does not use UDP/319 or UDP/320.

Chrony disciplines the host clock. PTP² advertises authenticated clock
measurements from a ROKO node identity.

## Useful checks

```bash
./bin/roko-edge-doctor
./bin/roko-rpc-health --rpc http://127.0.0.1:9944 --json
./bin/roko-time-health
```
