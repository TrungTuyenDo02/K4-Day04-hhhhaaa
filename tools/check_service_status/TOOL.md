---
name: check_service_status
track: core
kind: local_status
provider: mock_status_page
requires_env: []
inputs: [service, environment]
outputs: [service, environment, status, incident]
side_effect: false
---
# check_service_status

Reads the deterministic mock status page for a named shared service and
environment. It does not diagnose a single employee device.
