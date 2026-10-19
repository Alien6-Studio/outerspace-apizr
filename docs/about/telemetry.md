<span id="telemetry-local-preview-and-public-contract"></span>

# Telemetry and privacy

**Telemetry is optional.** The VS Code companion can send bounded usage counts
when the editor permits telemetry. Set `apizr.telemetry.enabled` to `false` to
disable it. Apizr 0.4.6 CLI and Python keep their optional counters local and
off by default.

<span id="approved-policy"></span>

## Privacy guarantees

Alien6 Studio is responsible for Apizr's telemetry policy. It follows the
[GDPR](https://www.cnil.fr/fr/conformite-rgpd-information-des-personnes-et-transparence)
principles of transparency, purpose limitation, data minimization and limited
retention:

- **Your choice:** enabling telemetry is optional; disabling it clears the counters.
- **A defined purpose:** usage counts help improve inspection, experiment history,
  tracking and REST/MCP generation.
- **Minimal data:** reports contain only an operation, its outcome, a count and
  the interface used (`cli`, `sdk` or `vscode`). They contain no user or installation
  identifier, source code, paths, experiment data, parameters, metrics or
  error messages.
- **No profiling:** counts describe operations, not people or installations.
- **Local controls:** counters exist only for the current command or capture
  scope. Pending extension reports stay in memory and are discarded on opt-out
  or editor shutdown; reports are never written to disk.

<span id="receiving-contract-and-reusable-conformance-fixtures"></span>

The [report schema](../specs/apizr-telemetry-v1.schema.json) defines the allowed
fields. Website analytics have separate consent controls.

## Control telemetry

```sh
apizr telemetry status
apizr telemetry enable
apizr telemetry preview
apizr telemetry disable
```

These commands work without a project. `enable` and `disable` save only your
consent preference. `preview` shows the report and `transmission_available: false`.
A new command has an empty report because counters are not saved between processes.

To preview the counters from an actual inspection:

```sh
APIZR_TELEMETRY=1 APIZR_TELEMETRY_PREVIEW=1 apizr experiment inspect model.py
```

The preview appears on stderr; normal command output is unchanged.
`APIZR_TELEMETRY=0` disables collection. CI and generated services never opt in.
A saved opt-out takes precedence over `APIZR_TELEMETRY=1`.

## Python and VS Code

In Python, use `apizr.telemetry.capture()` and inspect `usage.preview()` inside
the capture scope.

In VS Code, `apizr.telemetry.enabled` defaults to `true`. Collection still
requires VS Code’s telemetry permission and telemetry level `all`. Set the Apizr
setting to `false` to opt out. Disabling either control clears the preview and
prevents collection and cancels pending sends; a saved CLI opt-out also remains
effective for reports produced by the engine. Delivery failures do not interrupt
your work. **Apizr: Telemetry status** shows whether sending is enabled and the
last delivery result.
