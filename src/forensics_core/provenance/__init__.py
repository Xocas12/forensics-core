"""Fetch logging, checksums, the SOURCES.yaml registry, and the network policy (contact
header, per-host rate limits, never-fetch-twice cache). Nothing enters a pipeline without
a SOURCES.yaml entry; every fetch attempt is logged, successful or not."""
