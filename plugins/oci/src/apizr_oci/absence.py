"""Confirm an ambiguous Docker diagnostic through the exact HTTPS OCI endpoint.

Executed in a bounded child process: DNS and slow reads cannot outlive the
operation deadline. Only the already snapshotted explicit credentials are used.
Bearer challenges remain refused; no token realm or redirect receives secrets.
"""

import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ambiguous response")
        result[key] = value
    return result


def confirm(reference: str, work: Path, timeout: float) -> bool:
    # The parent permits only its validated PushRequest's exact repository.
    registry, repository = reference.split("/", 1)
    repository, tag = repository.rsplit(":", 1)
    config = json.loads(
        (work / "docker-config/config.json").read_bytes(),
        object_pairs_hook=unique_object,
    )
    auth = config["auths"][registry]["auth"]
    ca = work / "registry-ca.pem"
    context = ssl.create_default_context(cafile=str(ca) if ca.exists() else None)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        NoRedirect(),
        urllib.request.HTTPSHandler(context=context),
    )
    request = urllib.request.Request(
        f"https://{registry}/v2/{repository}/manifests/{tag}",
        headers={
            "Authorization": "Basic " + auth,
            "Accept": "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json",
        },
    )
    try:
        with opener.open(request, timeout=timeout):
            return False
    except urllib.error.HTTPError as error:
        with error:
            if error.code != 404:
                return False
            raw = error.read(65537)
        if len(raw) > 65536:
            return False
        response = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(response, dict) or set(response) != {"errors"}:
            return False
        errors = response["errors"]
        return (
            isinstance(errors, list)
            and len(errors) == 1
            and isinstance(errors[0], dict)
            and not set(errors[0]) - {"code", "message", "detail"}
            and errors[0].get("code") == "MANIFEST_UNKNOWN"
            and isinstance(errors[0].get("message"), str)
        )


def main() -> int:
    try:
        if confirm(sys.argv[1], Path.cwd(), float(sys.argv[2])):
            print("absent")
            return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        pass
    return 1


if __name__ == "__main__":
    sys.exit(main())
