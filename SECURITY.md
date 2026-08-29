# Security Policy

## Supported Versions

Only the latest release is supported. Please update to the latest version before reporting an issue.

## Reporting a Vulnerability

This integration only reads publicly published data over HTTPS — it does not handle credentials, personal data, or write access to any external system. It talks to three hosts: `lindas.admin.ch` (hydrological data) and `environment.ld.admin.ch` (bathing water quality), both operated by the Swiss federal administration, and `tecdottir.metaodi.ch`, a community-run third-party API that republishes the City of Zurich lake temperatures. Every request consists of a fixed query or a station code; the location and radius you configure are applied locally and are never sent anywhere. If you still believe you have found a security issue (e.g. in how data is parsed or how entities are exposed), please report it privately via [GitHub Security Advisories](../../security/advisories/new) rather than opening a public issue.

For anything that is not security-sensitive (bugs, feature requests), please use the regular [Issues](../../issues) tab instead.
