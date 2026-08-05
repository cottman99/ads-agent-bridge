import hashlib

from tools.release.verify_pypi_artifacts import compare_digests, local_digests


def test_release_artifact_hash_comparison(tmp_path) -> None:
    wheel = tmp_path / "example-1.0-py3-none-any.whl"
    sdist = tmp_path / "example-1.0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    local = local_digests(tmp_path)
    payload = {
        "urls": [
            {"filename": name, "digests": {"sha256": digest}}
            for name, digest in local.items()
        ]
    }

    assert compare_digests(local, payload)["ok"] is True

    payload["urls"][0]["digests"]["sha256"] = hashlib.sha256(b"different").hexdigest()
    assert compare_digests(local, payload)["ok"] is False
