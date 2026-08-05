# Changelog

All notable changes to cns-monitor will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- 21 new tests for `CNSWatcher` (`test_watcher.py`) — SignalEvent parsing, filesystem scanning, deduplication, callback registration
- Total tests: 17 → 38

## [0.1.0] - 2026-08-04

### Added
- `CNSWatcher` — polling-based filesystem watcher for USCP JSON packets
- `SignalEvent` — structured representation of observed packets
- `CNSStats` — real-time statistics: signal frequency, latency estimation, intent distribution
- `CNSDisplay` — rich terminal UI with live signal feed, stats tables, and priority coloring
- CLI entry point with `--watch`, `--interval`, `--inbox`, `--outbox` options
- 17 initial tests covering stats tracking and event recording
