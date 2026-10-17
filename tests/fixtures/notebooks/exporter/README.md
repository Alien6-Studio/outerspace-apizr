# Exporter baseline before legacy removal

These exact notebook bytes, nbconvert exports and Black-formatted scripts were
captured from `7efec77135002afe81e039cb723b2e148424f791`, before moving the exporter
from `modules/notebook_transformr` to `notebooks`. No notebook was executed.
`baseline.json` retains original paths, selection and SHA-256 identities.

The original magic refusal remains a refusal. The complex pricing notebook
selects `deploy` and excludes `explore`, as its historical YAML configuration did.
These golden bytes must not be regenerated merely to make a changed exporter pass.
