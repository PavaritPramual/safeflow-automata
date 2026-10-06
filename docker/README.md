# Home Assistant lab

Run `scripts/setup-local.ps1` first to generate ignored local API credentials.
Start the SafeFlow backend, then `docker compose -f docker/compose.yaml up -d`.

This dedicated simulated-home container is bound to localhost:8123, capped at
1.5 GiB, and pinned by image tag/digest. Account data lives in ignored `ha-data`;
tracked custom components call SafeFlow. Switches queue commands without directly
mutating the home. See [the guide](../docs/guides/smart-home.md).

Historical Sinergym instructions are [archived](../archive/sinergym/docker-workflow.md).
The container cap does not certify whole-system operation on an 8 GB host.
