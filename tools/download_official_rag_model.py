"""Download and verify the pinned official bge-m3 distribution; never import it.

Run with python -I. Each response is saved in its own new empty directory under
.tmp/rag-models/. This script does not change DNS/proxies/TLS, call Ollama pull,
run downloaded content, or write to a container/model volume.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / ".tmp" / "rag-models"
REGISTRY = "https://registry.ollama.ai/v2/library/bge-m3"
MODEL_DIGEST = "sha256:daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c"
EXPECTED = {
    MODEL_DIGEST: 1157671200,
    "sha256:a406579cd136771c705c521db86ca7d60a6f3de7c9b5460e6193a2df27861bde": 1068,
    "sha256:0c4c9c2a325fb1cdafec606e6809cb745f1cb26a6d919994400d27372303e276": 337,
}


def check_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not (host == "registry.ollama.ai" or host.endswith(".r2.cloudflarestorage.com"))):
        raise RuntimeError("Refused nonofficial or non-HTTPS download destination")


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(OfficialRedirects())


def isolated_file(name: str) -> Path:
    directory = DESTINATION / (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    return directory / name


def download(url: str, name: str, *, digest: str | None = None,
             size: int | None = None, maximum: int | None = None) -> Path:
    check_url(url)
    path = isolated_file(name)
    partial = path.with_suffix(path.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "CRMBOT-official-model-verifier/1.0"})
    sha = hashlib.sha256()
    received = 0
    last_report = time.monotonic()
    with OPENER.open(request, timeout=60) as response, partial.open("xb") as output:
        check_url(response.url)
        if response.status != 200:
            raise RuntimeError("Official download did not return HTTP 200")
        length = response.headers.get("Content-Length")
        if size is not None and length is not None and int(length) != size:
            raise RuntimeError("Unexpected Content-Length")
        print("Downloading", name, "from", urllib.parse.urlsplit(response.url).hostname, flush=True)
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            received += len(chunk)
            if (size is not None and received > size) or (maximum is not None and received > maximum):
                raise RuntimeError("Response exceeded expected size")
            output.write(chunk)
            sha.update(chunk)
            if time.monotonic() - last_report >= 20:
                print("Progress", name, received, "bytes", flush=True)
                last_report = time.monotonic()
    actual = "sha256:" + sha.hexdigest()
    if size is not None and received != size:
        raise RuntimeError("Downloaded size mismatch; partial retained, not imported")
    if digest is not None and actual != digest:
        raise RuntimeError("SHA-256 mismatch; partial retained, not imported")
    partial.rename(path)
    print("Verified", actual, received, str(path), flush=True)
    return path


def main() -> None:
    manifest_path = download(REGISTRY + "/manifests/latest", "manifest.json", maximum=65536)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = [manifest["config"], *manifest["layers"]]
    actual = {entry["digest"]: entry["size"] for entry in entries}
    if actual != EXPECTED or len(entries) != len(EXPECTED):
        raise RuntimeError("Official manifest differs from the pinned reviewed distribution")
    if manifest["schemaVersion"] != 2:
        raise RuntimeError("Unsupported manifest schema")
    results = {"manifest": str(manifest_path)}
    for entry in entries:
        digest = entry["digest"]
        results[digest] = str(download(REGISTRY + "/blobs/" + digest,
            digest.replace(":", "-"), digest=digest, size=entry["size"]))
    print("VERIFIED_ARTIFACTS", json.dumps(results), flush=True)


def import_verified() -> None:
    """Copy only reviewed official artifacts into the one new model volume."""
    container = "crmbot-rag-v2-ollama-1"
    inspection = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
    if inspection["Config"]["Labels"].get("com.docker.compose.project") != "crmbot-rag-v2":
        raise RuntimeError("Target is not the isolated project")
    mounts = [m for m in inspection["Mounts"] if m["Destination"] == "/root/.ollama"]
    if len(mounts) != 1 or mounts[0].get("Name") != "crmbot-rag-v2_rag_v2_ollama_models":
        raise RuntimeError("Unexpected model volume; no files imported")
    paths = {}
    for digest, expected_size in EXPECTED.items():
        candidates = list(DESTINATION.glob("*/" + digest.replace(":", "-")))
        if len(candidates) != 1:
            raise RuntimeError("Require exactly one verified file per blob")
        path = candidates[0]
        sha = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                sha.update(chunk)
        if path.stat().st_size != expected_size or "sha256:" + sha.hexdigest() != digest:
            raise RuntimeError("Host blob failed repeat verification")
        paths[digest] = path
    manifests = list(DESTINATION.glob("*/manifest.json"))
    if len(manifests) != 1:
        raise RuntimeError("Require exactly one reviewed manifest")
    manifest_path = manifests[0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if {e["digest"]: e["size"] for e in [manifest["config"], *manifest["layers"]]} != EXPECTED:
        raise RuntimeError("Manifest mismatch")
    staging = "/root/.ollama/rag-import-" + uuid.uuid4().hex
    subprocess.run(["docker", "exec", container, "mkdir", staging], check=True)
    for digest, path in paths.items():
        name = digest.replace(":", "-")
        target = staging + "/" + name
        subprocess.run(["docker", "cp", str(path), container + ":" + target], check=True)
        output = subprocess.check_output(["docker", "exec", container, "sha256sum", target], text=True)
        if output.split()[0] != digest.split(":", 1)[1]:
            raise RuntimeError("In-volume SHA verification failed; manifest not installed")
        print("Verified in new model volume", digest, flush=True)
    subprocess.run(["docker", "cp", str(manifest_path), container + ":" + staging + "/manifest.json"], check=True)
    output = subprocess.check_output(["docker", "exec", container, "sha256sum", staging + "/manifest.json"], text=True)
    if output.split()[0] != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
        raise RuntimeError("In-volume manifest bytes mismatch")
    blobs = "/root/.ollama/models/blobs"
    manifest_dir = "/root/.ollama/models/manifests/registry.ollama.ai/library/bge-m3"
    subprocess.run(["docker", "exec", container, "mkdir", "-p", blobs, manifest_dir], check=True)
    for digest in paths:
        name = digest.replace(":", "-")
        subprocess.run(["docker", "exec", container, "mv", "-n", staging + "/" + name, blobs + "/" + name], check=True)
        output = subprocess.check_output(["docker", "exec", container, "sha256sum", blobs + "/" + name], text=True)
        if output.split()[0] != digest.split(":", 1)[1]:
            raise RuntimeError("Final blob mismatch; manifest not installed")
    subprocess.run(["docker", "exec", container, "mv", "-n", staging + "/manifest.json", manifest_dir + "/latest"], check=True)
    output = subprocess.check_output(["docker", "exec", container, "sha256sum", manifest_dir + "/latest"], text=True)
    if output.split()[0] != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
        raise RuntimeError("Final manifest mismatch")
    print("Official files imported; embedding compatibility remains unverified", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-verified", action="store_true", help="Import previously verified artifacts into the isolated new model volume")
    args = parser.parse_args()
    import_verified() if args.import_verified else main()
