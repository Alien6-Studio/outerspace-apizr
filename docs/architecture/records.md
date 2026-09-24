# Engineering archive

These records preserve evidence from particular revisions. Test counts, Python
support ranges and vulnerability findings describe those revisions, not the
current checkout. Their published URLs remain available for existing links.

| Record | What it documents |
| --- | --- |
| [macOS extension cleanup](extension-cleanup-macos.md) | Synchronized reproduction of redundant group signalling and the bounded cleanup regression |
| [Original 0.2 baseline](0.2-baseline.md) | The starting pipeline and quality results before foundation hardening |
| [Foundation verification](0.2-hardening.md) | Package normalization, tests and the findings still open at that stage |
| [Historical dependency audit](foundation-security-audit.md) | Vulnerabilities in the earlier dependency graph before runtime rationalization |
| [Capability IR verification](capability-ir-v1-verification.md) | The independent IR implementation, compatibility checks and byte comparisons |
| [0.2.0 post-release verification](0.2.0-post-release-verification.md) | Published files versus later master builds, full CI evidence and remaining maintenance decisions |

For current work, use the [development checks](../getting-started/developer-guide/setup.md),
[migration guidance](../getting-started/developer-guide/releases.md) and
[security baseline](security-baseline.md). The
[Capability IR specification](capability-ir-v1.md),
[legacy behavior contract](legacy-behavior-contract.md) and
[artifact principles](artifact-principles.md) remain under technical reference.
