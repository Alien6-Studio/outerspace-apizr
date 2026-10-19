"""One assertion over all direct and governed generated artifact closures."""


def assert_telemetry_free(files):
    for name, raw in files.items():
        assert "/telemetry/" not in name
        for token in (
            b"apizr.telemetry",
            b"APIZR_TELEMETRY",
            b"telemetry.outerspace.sh",
            b"apizr_usage_capture",
        ):
            assert token not in raw, (name, token)
