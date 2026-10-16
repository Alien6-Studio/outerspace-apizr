# Migrate historical pipeline plugins

The `apizr.pipeline.v1` entrypoint group, `PipelinePlugin`, step engine and
`--plugin` generation hook were removed in 0.4.6 along with the legacy pipeline.
Installed historical extensions no longer activate through Apizr. There is no
automatic conversion of a mutable pipeline hook into a trusted extension.

Package explicit operations with the [current extension protocol](../../architecture/extension-packaging-v04.md)
and the [plugin guide](../../reference/plugin-authors.md). Scientific recognizers
can use the [provider contract](../../reference/scientific-providers.md).
An application build step that transforms files should remain an explicit,
reviewed build command outside Apizr's evidence contracts. See the
[migration table](../../releases/migrate-0.4.6.md#removed-generation-pipeline).
