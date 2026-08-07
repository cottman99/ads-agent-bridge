from pathlib import Path

from ads_agent_bridge import processes


def _fake_process(proc_root: Path, pid: int, name: str, environment: dict[str, str]) -> None:
    process_root = proc_root / str(pid)
    process_root.mkdir()
    (process_root / "comm").write_text(f"{name}\n", encoding="utf-8")
    payload = b"\0".join(f"{key}={value}".encode() for key, value in environment.items()) + b"\0"
    (process_root / "environ").write_bytes(payload)
    (process_root / "status").write_text(f"Name:\t{name}\nPPid:\t1\n", encoding="utf-8")


def test_linux_process_discovery_requires_exact_nonce_slot_and_ads_process_name(tmp_path: Path) -> None:
    environment = {
        "ADS_AGENT_MANAGED_SESSION_ID": "owned-nonce",
        "ADS_AGENT_SLOT": "blind-slot",
    }
    _fake_process(tmp_path, 40, "hpeesofemx", environment)
    _fake_process(tmp_path, 41, "hpeesofde", environment)
    _fake_process(tmp_path, 42, "aglmpsel_exe", environment)
    _fake_process(
        tmp_path,
        43,
        "hpeesofde",
        {**environment, "ADS_AGENT_MANAGED_SESSION_ID": "different"},
    )
    _fake_process(
        tmp_path,
        44,
        "hpeesofde",
        {**environment, "ADS_AGENT_SLOT": "different-slot"},
    )

    matches = processes._linux_managed_ads_processes(
        "owned-nonce",
        "blind-slot",
        proc_root=tmp_path,
    )

    assert matches == [
        {"pid": 41, "process_name": "hpeesofde", "role": "design-environment"},
        {"pid": 40, "process_name": "hpeesofemx", "role": "ads-runtime"},
    ]

    host_matches = processes._linux_managed_host_processes(
        "owned-nonce",
        "blind-slot",
        proc_root=tmp_path,
    )
    assert host_matches == [
        {
            "pid": 41,
            "parent_pid": 1,
            "process_name": "hpeesofde",
            "role": "design-environment",
        },
        {
            "pid": 40,
            "parent_pid": 1,
            "process_name": "hpeesofemx",
            "role": "ads-runtime",
        },
        {
            "pid": 42,
            "parent_pid": 1,
            "process_name": "aglmpsel_exe",
            "role": "managed-child",
        },
    ]


def test_windows_descendant_selection_keeps_only_the_reserved_launch_tree() -> None:
    entries = {
        100: (1, "ads.exe"),
        101: (100, "hpeesofemx.exe"),
        102: (101, "hpeesofde.exe"),
        103: (102, "aglmpsel_exe.exe"),
        200: (1, "hpeesofde.exe"),
    }

    assert processes._descendant_pids(100, entries) == {100, 101, 102, 103}
