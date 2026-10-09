"""Local delivery preparation only; no credentials are opened and no effects run."""

import hashlib
import os
import stat
from pathlib import Path
from typing import Any

from apizr.delivery_batch import BatchError, BatchRequest, inspect_batch
from apizr.delivery_batch.models import destination_key
from apizr.operator_policy import OperatorPolicy, decide
from apizr.plugins.local.models import Installation, PluginError
from apizr.plugins.local.store import validate_directory
from apizr.publication_contracts import (
    AdmitRequest,
    AttestRequest,
    ObserveRequest,
    PublishRequest,
)
from apizr.workspace.files import directory_fd

from .diagnostics import Checks


def metadata(
    path: str,
    *,
    executable: bool = False,
    directory: bool = False,
    socket: bool = False,
) -> None:
    """Only lstat/access: never open auth, trust or private-key contents."""
    value = Path(path)
    if not value.is_absolute() or ".." in value.parts:
        raise ValueError()
    with directory_fd(value.parent) as parent:
        info = os.stat(value.name, dir_fd=parent, follow_symlinks=False)
        predicate = (
            stat.S_ISDIR if directory else stat.S_ISSOCK if socket else stat.S_ISREG
        )
        if not predicate(info.st_mode) or (
            executable
            and not os.access(value.name, os.X_OK, dir_fd=parent, follow_symlinks=False)
        ):
            raise ValueError()


def check_delivery(
    request: BatchRequest,
    records: dict[str, Installation],
    authority: OperatorPolicy | None,
    checks: Checks,
) -> None:
    root = Path(request.evidence_root)
    try:
        if ".." in root.parts:
            raise ValueError()
        with directory_fd(root.parent):
            pass
        if os.path.lexists(root):
            metadata(str(root), directory=True)
            validate_directory(root)
        inspect_batch(request)
        checks.add(
            "delivery_evidence",
            "pass",
            "Local evidence identity and root structure valid; nothing created.",
        )
    except (BatchError, OSError, ValueError, PluginError):
        checks.add(
            "delivery_evidence",
            "fail",
            "Evidence root or retained identity invalid.",
            "Select a safe evidence root with an existing parent and matching retained state.",
        )
    for index, destination in enumerate(request.destinations, 1):
        prefix = f"destination_{index}"
        push, proof = destination.push, destination.proof
        try:
            metadata(push.docker.executable, executable=True)
            metadata(push.docker.socket, socket=True)
            if push.docker.buildx is not None:
                metadata(push.docker.buildx, executable=True)
            auths = [push.authentication]
            if proof is not None:
                metadata(proof.verification.tool.executable, executable=True)
                metadata(proof.transport.tool.executable, executable=True)
                metadata(proof.verification.trust_store, directory=True)
                metadata(proof.signing.key_file)
                auths.append(proof.transport.authentication)
            for auth in auths:
                metadata(auth.config_file)
                if auth.ca_file is not None:
                    metadata(auth.ca_file)
            checks.add(
                prefix + "_references",
                "pass",
                "Tool/auth/trust/key references structurally available; secret contents not read.",
            )
        except (OSError, ValueError):
            checks.add(
                prefix + "_references",
                "fail",
                "A required local tool or auth/trust/key reference is unavailable or unsafe.",
                "Review explicit references locally; doctor does not inspect credentials or execute tools.",
            )
        operations = [
            ("oci", "push", push),
            (
                "oci",
                "observe",
                ObserveRequest(
                    schema="apizr.observe-delivery/v1",
                    push=push,
                    expected_reference=destination.recovery_reference,
                ),
            ),
        ]
        if proof is not None:
            child = (
                root
                / hashlib.sha256(destination_key(push.destination).encode()).hexdigest()
            )
            # Admission uses repository identity, not a remote availability claim.
            # Before transfer there is no registry manifest digest; the immutable
            # local build digest is only a structurally valid authorization input.
            reference = (
                destination.recovery_reference
                or push.destination.rsplit(":", 1)[0] + "@" + push.image_id
            )
            assert push.delivery_manifest is not None
            common: dict[str, Any] = proof.verification.model_dump() | {
                "expected_reference": reference
            }
            operations.extend(
                [
                    (
                        "attest",
                        "attest",
                        AttestRequest(
                            schema="apizr.attest-delivery/v1",
                            build_result=str(root / "build.json"),
                            push_result=str(child / "push.json"),
                            docker=push.docker,
                            authentication=push.authentication,
                            output_dir=str(child / "proof"),
                            **proof.signing.model_dump(),
                            **common,
                        ),
                    ),
                    (
                        "attest",
                        "publish",
                        PublishRequest(
                            schema="apizr.publish-proof/v1",
                            proof_dir=str(child / "proof"),
                            transport=proof.transport,
                            **common,
                        ),
                    ),
                    (
                        "attest",
                        "admit",
                        AdmitRequest(
                            schema="apizr.admit-delivery/v1",
                            push_result=str(child / "push.json"),
                            delivery_manifest=push.delivery_manifest,
                            destination=push.destination,
                            artifact_reference=destination.selected_artifact
                            or reference,
                            transport=proof.transport,
                            docker=push.docker,
                            **common,
                        ),
                    ),
                ]
            )
        for kind, operation, arguments in operations:
            record = records.get(kind)
            decision = (
                decide(
                    authority,
                    record,
                    operation,
                    arguments.model_dump(mode="json", by_alias=True),
                )
                if record is not None
                else None
            )
            allowed = (
                decision is not None
                and decision.allowed
                and decision.code == "authorized"
            )
            checks.add(
                prefix + "_" + operation,
                "pass" if allowed else "fail",
                "Existing operator decision authorizes this exact installed identity and effect."
                if allowed
                else "Effect not authorized for the validated installed identity.",
                ""
                if allowed
                else "Review the explicit operator policy and selected installation; no grants are inferred.",
            )
    checks.add(
        "remote_availability",
        "skip",
        "Registry, Docker, signing and timestamp services were not contacted.",
    )
