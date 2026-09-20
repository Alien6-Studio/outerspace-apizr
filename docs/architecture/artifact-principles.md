# Artifact principles

Apizr artifacts should be independently hashable and attestable without requiring
an attestation implementation.

Generation takes explicit source, configuration and optional requirements inputs,
and writes explicit Python, JSON, requirements and container files. Analysis and
generation must not import supplied source or perform hidden network requests.
Generated artifacts should avoid timestamps, random identifiers and incidental
machine paths. Equal inputs in an equal dependency environment should yield equal
file contents; the result envelope's output directory is location-specific.

Dependency inference currently consults installed distribution metadata. Record
the Python and dependency environment or supply explicit requirements when
reproducing outputs. Dependency installation and container builds can access
networks separately from generation. Running a generated application imports
user code and requires trust; deterministic generation is not a runtime sandbox.

These principles require no attestation dependency, integration or new metadata
format. Existing analysis metadata and runtime semantics are retained.
