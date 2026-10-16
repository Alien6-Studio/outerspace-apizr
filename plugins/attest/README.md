# outerspace-apizr-attest

Apizr **0.4.6**: use the matching core and plugin versions together.

Sign, timestamp, transport and verify proofs of an OCI delivery.

This optional Apizr plugin runs in its own Python environment. Use the
[installation guide](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile)
to choose the matching catalog profile and verified target artifacts. The
[release record](https://github.com/Alien6-Studio/outerspace-apizr/blob/v0.4.6/docs/releases/0.4.6.md) describes the
functionality and validation for **Apizr 0.4.6**.

Installation does not activate a plugin or authorize its operations. Enable the
chosen version explicitly and supply the required operator policy. Existing
locks, activations and permissions are not migrated automatically.

See the [plugin guide](https://apizr.outerspace.sh/reference/attest-delivery-plugin/).
Python 3.11–3.15. GPL-3.0-or-later; the full license is included.
