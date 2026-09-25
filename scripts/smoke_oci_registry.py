"""Disposable authenticated TLS registry and two independent Docker daemons.

Run on a Docker host (including Desktop). Only resources created here are removed.
The installed-wheel proof runs inside the builder's disposable Linux environment.
"""

import argparse
import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def command(*args, timeout=600):
    result = subprocess.run(list(map(str, args)), capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-4000:])
    return result.stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attest", action="store_true")
    parser.add_argument("--artifacts", action="store_true")
    args = parser.parse_args()
    if args.artifacts:
        args.attest = True
    args.output.mkdir(parents=True, exist_ok=False)
    prefix = "apizr-registry-" + uuid.uuid4().hex[:12]
    network, volume = prefix + "-net", prefix + "-data"
    image = prefix + ":fixture"
    containers = []
    command("docker", "network", "create", network)
    command("docker", "volume", "create", volume)
    try:
        with tempfile.TemporaryDirectory() as directory:
            context = Path(directory)
            (context / "Dockerfile").write_text("""FROM docker:29-dind
RUN apk add --no-cache python3 py3-pip git git-daemon openssl apache2-utils && python3 -m pip install --break-system-packages uv==0.12.0
""")
            if args.attest:
                (context / "Dockerfile").write_text("""FROM docker:29-dind AS docker
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip git openssl apache2-utils ca-certificates curl iptables util-linux pigz xz-utils && rm -rf /var/lib/apt/lists/* && python3 -m pip install --break-system-packages uv==0.12.0
COPY --from=docker /usr/local/bin/ /usr/local/bin/
COPY --from=docker /usr/local/libexec/ /usr/local/libexec/
VOLUME /var/lib/docker
RUN mkdir /opt/attest && curl -fL --max-time 90 https://github.com/Alien6-Studio/continuum-attest/releases/download/v0.1.0/attest-v0.1.0-linux-x86_64.tar.gz -o /opt/attest/archive.tar.gz && echo 'f51201745b30be356e066cd615a7ef41fed92b17cf720ceb03e7f2a4d58505ad  /opt/attest/archive.tar.gz' | sha256sum -c - && tar -xzf /opt/attest/archive.tar.gz -C /opt/attest attest && /opt/attest/attest --version
""")
            if args.artifacts:
                with (context / "Dockerfile").open("a") as stream:
                    stream.write(
                        "RUN mkdir /opt/oras && curl -fL --max-time 90 https://github.com/oras-project/oras/releases/download/v1.3.4/oras_1.3.4_linux_amd64.tar.gz -o /opt/oras/archive.tar.gz && echo 'f27adb935022d94df8dc77719c322dda592c78a0d57a6f7dcdd8d900b248c454  /opt/oras/archive.tar.gz' | sha256sum -c - && tar -xzf /opt/oras/archive.tar.gz -C /opt/oras oras && /opt/oras/oras version\n"
                    )
            command(
                "docker",
                "build",
                *(["--platform", "linux/amd64"] if args.attest else []),
                "--tag",
                image,
                context,
            )
        # Credentials are generated and remain inside the disposable volume.
        preparation = """set -eu
mkdir -p /proof/certs /proof/auth /proof/bin
cp /repo/scripts/oci_build_observer.py /proof/bin/docker
chmod 700 /proof/bin/docker
openssl req -x509 -newkey rsa:2048 -nodes -keyout /proof/certs/key.pem -out /proof/certs/ca.crt -days 1 -subj /CN=registry.test -addext subjectAltName=DNS:registry.test,DNS:registry-untrusted.test,DNS:registry-backend.test >/dev/null 2>&1
python3 - <<'PY'
import base64,json,secrets,subprocess
from pathlib import Path
password=secrets.token_hex(24)
p=Path('/proof/auth/config.json')
p.write_text(json.dumps({'auths':{'registry.test:5443':{'auth':base64.b64encode(('fixture:'+password).encode()).decode()}}}))
p.chmod(0o600)
r=subprocess.run(['htpasswd','-Bni','fixture'],input=password+'\\n',text=True,capture_output=True,check=True)
Path('/proof/auth/htpasswd').write_text(r.stdout)
password=secrets.token_hex(24)
Path('/proof/auth/read-config.json').write_text(json.dumps({'auths':{'registry.test:5443':{'auth':base64.b64encode(('reader:'+password).encode()).decode()}}}))
r=subprocess.run(['htpasswd','-Bni','reader'],input=password+'\\n',text=True,capture_output=True,check=True)
with Path('/proof/auth/htpasswd').open('a') as out: out.write(r.stdout)
Path('/proof/zot.json').write_text(json.dumps({'distSpecVersion':'1.1.1','storage':{'rootDirectory':'/var/lib/registry'},'http':{'address':'0.0.0.0','port':'5443','tls':{'cert':'/proof/certs/ca.crt','key':'/proof/certs/key.pem'},'auth':{'htpasswd':{'path':'/proof/auth/htpasswd'}},'accessControl':{'repositories':{'**':{'policies':[{'users':['fixture'],'actions':['read','create','update','delete']},{'users':['reader'],'actions':['read']}]}}}},'log':{'level':'error'}}))
PY
"""
        command(
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "sh",
            "--mount",
            f"type=volume,src={volume},dst=/proof",
            "--mount",
            f"type=bind,src={REPO},dst=/repo,readonly",
            image,
            "-c",
            preparation,
        )
        registry = prefix + "-registry"
        containers.append(registry)
        command(
            "docker",
            "run",
            "--detach",
            "--name",
            registry,
            "--network",
            network,
            "--network-alias",
            "registry.test",
            "--network-alias",
            "registry-untrusted.test",
            "--network-alias",
            "registry-backend.test",
            "--mount",
            f"type=volume,src={volume},dst=/proof,readonly",
            "--env",
            "REGISTRY_HTTP_ADDR=0.0.0.0:5443",
            "--env",
            "REGISTRY_HTTP_TLS_CERTIFICATE=/proof/certs/ca.crt",
            "--env",
            "REGISTRY_HTTP_TLS_KEY=/proof/certs/key.pem",
            "--env",
            "REGISTRY_AUTH=htpasswd",
            "--env",
            "REGISTRY_AUTH_HTPASSWD_REALM=fixture",
            "--env",
            "REGISTRY_AUTH_HTPASSWD_PATH=/proof/auth/htpasswd",
            *(
                [
                    "ghcr.io/project-zot/zot:v2.1.21@sha256:6b69512c00dceaad05b1144e6079aac6aa7309d7fd200f9947ecb1de09cf48c8",
                    "serve",
                    "/proof/zot.json",
                ]
                if args.artifacts
                else ["registry:3"]
            ),
        )
        for role in ("builder", "consumer"):
            name = prefix + "-" + role
            containers.append(name)
            command(
                "docker",
                "run",
                "--detach",
                "--privileged",
                "--name",
                name,
                "--network",
                network,
                "--network-alias",
                role + ".test",
                "--mount",
                f"type=volume,src={volume},dst=/proof",
                "--mount",
                f"type=bind,src={REPO},dst=/repo,readonly",
                "--entrypoint",
                "sh",
                image,
                "-c",
                "mkdir -p /etc/docker/certs.d/registry.test:5443; cp /proof/certs/ca.crt /etc/docker/certs.d/registry.test:5443/ca.crt; exec dockerd --host=unix:///proof/"
                + role
                + ".sock",
            )
        builder = prefix + "-builder"
        deadline = time.monotonic() + 60
        for role in ("builder", "consumer"):
            while True:
                try:
                    result = subprocess.run(
                        [
                            "docker",
                            "exec",
                            builder,
                            "docker",
                            "--host",
                            "unix:///proof/" + role + ".sock",
                            "info",
                        ],
                        capture_output=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        break
                except subprocess.TimeoutExpired:
                    pass  # readiness probe timed out; the original deadline still applies
                if time.monotonic() >= deadline:
                    raise RuntimeError("fixture daemon unavailable")
                time.sleep(0.2)
        with (args.output / "proof.log").open("wb") as log:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "--env",
                    "APIZR_REGISTRY_PROOF=1",
                    "--env",
                    "APIZR_ATTEST_PROOF=" + ("1" if args.attest else "0"),
                    "--env",
                    "APIZR_ARTIFACT_PROOF=" + ("1" if args.artifacts else "0"),
                    "--env",
                    "PATH=/proof/bin:/usr/local/bin:/usr/bin:/bin",
                    builder,
                    "python3",
                    "/repo/scripts/smoke_oci_plugin.py",
                    "--work-dir",
                    "/proof/work",
                    "--docker-socket",
                    "/proof/builder.sock",
                    "--buildx",
                    "/usr/local/libexec/docker/cli-plugins/docker-buildx",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=1500,
            )
        if args.artifacts and result.returncode == 0:
            from smoke_artifact_consumer import consume

            consume(command, args.output, prefix, network, volume, image, REPO)
        for name in (
            "artifact-results.json",
            "artifact-refusals.json",
            "results.json",
            "build-diagnostic.log",
            "build-observation.json",
            "push-results.json",
            "attest-results.json",
            "attest-refusals.json",
            "attest-tool.json",
            "push-refusals.json",
            "push-interruption.json",
            "refusals.json",
            "interruption.json",
        ):
            subprocess.run(
                [
                    "docker",
                    "cp",
                    builder + ":/proof/work/" + name,
                    str(args.output / name),
                ],
                capture_output=True,
                timeout=10,
            )
        (args.output / "outcome.json").write_text(
            json.dumps({"exit_code": result.returncode})
        )
        if result.returncode:
            raise RuntimeError("installed registry proof failed; see proof.log")
        print(
            "PASS authenticated HTTPS push and digest retrieval in independent Docker environments"
        )
    finally:
        for container in reversed(containers):
            subprocess.run(
                ["docker", "rm", "--force", "--volumes", container],
                capture_output=True,
                timeout=30,
            )
        command("docker", "volume", "rm", volume)
        command("docker", "network", "rm", network)
        subprocess.run(
            ["docker", "image", "rm", image], capture_output=True, timeout=30
        )


if __name__ == "__main__":
    main()
