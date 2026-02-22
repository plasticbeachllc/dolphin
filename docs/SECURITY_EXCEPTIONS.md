# Security Exceptions

This document records security advisories that are intentionally ignored in CI
(`security-scan.yml`), along with the rationale, current status, and a
re-evaluation date.

---

## Active Exceptions

### CVE-2026-0994 — Protobuf denial-of-service

| Field              | Value                                      |
| ------------------ | ------------------------------------------ |
| **Advisory**       | CVE-2026-0994                              |
| **Package**        | `protobuf`                                 |
| **Severity**       | Medium (DoS)                               |
| **Ignored since**  | 2026-02                                    |
| **Re-evaluate by** | 2026-05 (or when upstream publishes a fix) |

**Description**: A denial-of-service vulnerability in the protobuf library
affecting protobuf parsing under certain untrusted-input conditions.

**Why we accept this risk**: Dolphin uses protobuf exclusively as a transitive
dependency of the OpenTelemetry OTLP exporter (`opentelemetry-exporter-otlp`).
Protobuf-encoded data in Dolphin's context is telemetry sent _to_ a trusted
collector (Jaeger/Grafana), never parsed from untrusted external sources.
The DoS vector is therefore not reachable in normal deployment.

**Status**: No upstream fix published as of the exception date. Tracked at
<https://github.com/protocolbuffers/protobuf/issues> — monitor for a release
that resolves this CVE.

**CI reference**: `.github/workflows/security-scan.yml:28`

---

### GHSA-7gcm-g887-7qv7

| Field              | Value                        |
| ------------------ | ---------------------------- |
| **Advisory**       | GHSA-7gcm-g887-7qv7          |
| **Package**        | TBD — see investigation note |
| **Severity**       | Unknown                      |
| **Ignored since**  | 2026-02                      |
| **Re-evaluate by** | 2026-04                      |

**Description**: Advisory details were not publicly available when this
exception was added.

**Why we accept this risk**: Pending investigation. This exception should be
reviewed — either document the rationale properly once details are available,
or remove the ignore and address the underlying package version.

**Action required**: Run `uv run pip-audit --local` without the ignore flag,
identify which package is affected, and update this entry with full details.

**CI reference**: `.github/workflows/security-scan.yml:28`

---

## Process

When adding a new exception:

1. Add `--ignore-vuln <ID>` to the relevant CI step.
2. Add an entry to this file with: advisory ID, affected package, severity,
   rationale, and a concrete re-evaluation date (≤ 3 months out).
3. Set a calendar reminder for the re-evaluation date.
4. At re-evaluation: either remove the exception (fix applied upstream) or
   refresh the rationale and extend the date with documented reasoning.
