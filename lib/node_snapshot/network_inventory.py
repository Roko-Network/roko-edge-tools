"""Collect interface capabilities and ROKO-relevant listener classes without addresses."""

from __future__ import annotations

import os

from node_snapshot.probe_io import read_int, read_text

# Ports used by the ROKO node, its tooling, and time services (installer defaults).
PORTS_OF_INTEREST = {9944: "rpc", 9933: "rpc-legacy", 9615: "prometheus", 30333: "p2p",
                     123: "ntp", 319: "ptp-event", 320: "ptp-general"}
P2P_PORT = 30333
MAX_INTERFACES = 32
TCP_LISTEN, TCP_ESTABLISHED, UDP_UNCONNECTED = "0A", "01", "07"


def _interface_kind(path: str) -> str:
    if os.path.isdir(os.path.join(path, "wireless")):
        return "wireless"
    if os.path.exists(os.path.join(path, "device")):
        return "physical"
    if os.path.isdir(os.path.join(path, "bonding")):
        return "bond"
    if os.path.isdir(os.path.join(path, "bridge")):
        return "bridge"
    return "virtual"


LISTED_KINDS = ("physical", "wireless", "bond")


def collect_interfaces() -> tuple[list[dict], dict]:
    """Detail physical, wireless and bond links; count bridges and virtual links by kind."""
    root = "/sys/class/net"
    interfaces, other_counts = [], {}
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        path = os.path.join(root, name)
        kind = _interface_kind(path)
        if name == "lo":
            continue
        if kind not in LISTED_KINDS or len(interfaces) >= MAX_INTERFACES:
            other_counts[kind] = other_counts.get(kind, 0) + 1
            continue
        speed = read_int(os.path.join(path, "speed"))
        interfaces.append({
            "name": name[:32],
            "kind": kind,
            "operState": read_text(os.path.join(path, "operstate")),
            "speedMbps": speed if speed and speed > 0 else None,
            "duplex": read_text(os.path.join(path, "duplex")),
            "mtu": read_int(os.path.join(path, "mtu")),
            "rxErrors": read_int(os.path.join(path, "statistics/rx_errors")),
            "txErrors": read_int(os.path.join(path, "statistics/tx_errors")),
            "rxDropped": read_int(os.path.join(path, "statistics/rx_dropped")),
        })
    return interfaces, other_counts


def classify_bind_address(hex_address: str) -> str:
    """Classify a /proc/net address as loopback, all-interfaces or specific-address."""
    address = hex_address.upper()
    if set(address) == {"0"}:
        return "all-interfaces"
    if len(address) == 8:
        return "loopback" if address.endswith("7F") else "specific-address"
    if address == "0" * 24 + "01000000":
        return "loopback"
    if address.startswith("0" * 16 + "FFFF0000"):
        return "loopback" if address.endswith("7F") else "specific-address"
    return "specific-address"


def _socket_rows(name: str):
    for line in (read_text(f"/proc/net/{name}", limit=8 * 1024 * 1024) or "").splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4 or ":" not in fields[1]:
            continue
        local_addr, local_port = fields[1].rsplit(":", 1)
        remote_port = fields[2].rsplit(":", 1)[-1]
        yield local_addr, int(local_port, 16), int(remote_port, 16), fields[3]


def collect_listeners() -> dict:
    listeners, p2p_connections = set(), 0
    for table in ("tcp", "tcp6", "udp", "udp6"):
        for address, port, remote_port, state in _socket_rows(table):
            is_tcp = table.startswith("tcp")
            if is_tcp and state == TCP_ESTABLISHED and P2P_PORT in (port, remote_port):
                p2p_connections += 1
            listening = state == (TCP_LISTEN if is_tcp else UDP_UNCONNECTED)
            if listening and port in PORTS_OF_INTEREST:
                listeners.add((PORTS_OF_INTEREST[port], port, table[:3], classify_bind_address(address)))
    return {
        "listeners": [{"service": s, "port": p, "protocol": proto, "bindScope": scope}
                      for s, p, proto, scope in sorted(listeners, key=lambda item: (item[1], item[2], item[3]))],
        "p2pEstablishedTcp": p2p_connections,
    }


def collect_network() -> dict:
    route = read_text("/proc/net/route") or ""
    interfaces, other_counts = collect_interfaces()
    return {
        "interfaces": interfaces,
        "otherInterfaceCounts": other_counts,
        "hasIpv4DefaultRoute": any(line.split()[1:2] == ["00000000"] for line in route.splitlines()[1:]),
        "ipv6Enabled": bool(read_text("/proc/net/if_inet6")),
        **collect_listeners(),
    }
