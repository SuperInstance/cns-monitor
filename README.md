# 📡 CNS Monitor

Real-time traffic monitor for the **CNS (Central Nervous System)** ecosystem. Watches `cns_inbox` and `cns_outbox` directories for USCP (Universal Sensory/Command Packet) JSON signals and displays them live in a terminal dashboard.

Think `htop` for agent signals.

## Features

- **Live dashboard** — rich terminal UI with signal feed, intent distribution, and agent activity
- **Real-time stats** — signals/minute, average response latency, active agents
- **Priority highlighting** — CRITICAL signals in red, HIGH in yellow, etc.
- **Zero native deps** — pure Python polling, works anywhere
- **One-shot mode** — scan and print for scripting/CI use

## Install

```bash
pip install -e .
```

## Usage

```bash
# Live monitor with default paths (~/.hermes/cns_inbox, ~/.hermes/cns_outbox)
cns-monitor

# Custom paths
cns-monitor --inbox /path/to/inbox --outbox /path/to/outbox

# One-shot scan (prints results and exits)
cns-monitor --once

# Faster polling
cns-monitor --interval 0.25
```

## USCP Packet Format

```json
{
  "header": {
    "origin_id": "agent-name",
    "timestamp": "2026-08-04T22:10:00Z",
    "priority": "MEDIUM",
    "sequence_id": 1
  },
  "body": {
    "intent": "EXECUTE_PLAN",
    "payload": {
      "type": "command",
      "data": {}
    }
  },
  "signature": {
    "type": "USCP-v1",
    "checksum": "verified"
  }
}
```

## License

MIT
