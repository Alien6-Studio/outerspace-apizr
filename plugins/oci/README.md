# outerspace-apizr-oci

Build REST/MCP service images and explicitly publish a verified image.

This optional Apizr plugin runs in its own Python environment. Use the
[installation guide](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile)
to choose the matching catalog profile and verified target artifacts. The
[release record](https://apizr.outerspace.sh/releases/0.4.0/) identifies published
versions and candidate resources; package metadata alone is not a publication announcement.

Installation does not activate a plugin or authorize its operations. Enable the
chosen version explicitly and supply the required operator policy. Development
locks, activations and permissions are not migrated automatically.

See the [plugin guide](https://apizr.outerspace.sh/reference/oci-service-plugin/).
Python 3.11–3.14. GPL-3.0-or-later; the full license is included.
