"""Mandatory hard budgets checked before any model bytes are parsed."""

import os
import resource
import socket
from pathlib import Path
from typing import Any

MEMORY_BYTES = 768 * 1024**2
CPU_SECONDS = 60
FILE_BYTES = 64 * 1024**2
PROCESS_LIMIT = 32


def apply() -> None:
    for kind, value in [
        (resource.RLIMIT_AS, MEMORY_BYTES),
        (resource.RLIMIT_CPU, CPU_SECONDS),
        (resource.RLIMIT_FSIZE, FILE_BYTES),
        (resource.RLIMIT_NPROC, PROCESS_LIMIT),
        (resource.RLIMIT_NOFILE, 64),
        (resource.RLIMIT_CORE, 0),
    ]:
        resource.setrlimit(kind, (value, value))
    os.umask(0o077)


def status() -> dict[str, Any]:
    proc = {
        line.split(":", 1)[0]: line.split(":", 1)[1].strip()
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    }
    work = os.statvfs("/work")
    forbidden = [
        name
        for name in os.environ
        if any(
            token in name.upper()
            for token in [
                "SECRET",
                "TOKEN",
                "DATABASE",
                "PROXY",
                "CREDENTIAL",
                "COOKIE",
            ]
        )
    ]
    return {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "cap_eff": proc["CapEff"],
        "no_new_privs": proc["NoNewPrivs"],
        "seccomp": proc["Seccomp"],
        "network_devices": sorted(os.listdir("/sys/class/net")),
        "root_readonly": bool(os.statvfs("/").f_flag & os.ST_RDONLY),
        "input_readonly": bool(os.statvfs("/input").f_flag & os.ST_RDONLY)
        if Path("/input").exists()
        else None,
        "work_bytes": work.f_blocks * work.f_frsize,
        "forbidden_environment": forbidden,
        "memory_limit": resource.getrlimit(resource.RLIMIT_AS)[1],
        "cpu_limit": resource.getrlimit(resource.RLIMIT_CPU)[1],
        "pid_limit": resource.getrlimit(resource.RLIMIT_NPROC)[1],
        "file_limit": resource.getrlimit(resource.RLIMIT_FSIZE)[1],
    }


def require_sandbox(*, with_input: bool = True) -> dict[str, Any]:
    result = status()
    if (
        result["uid"] != 10001
        or result["cap_eff"] != "0000000000000000"
        or result["no_new_privs"] != "1"
        or result["seccomp"] != "2"
        or result["network_devices"] != ["lo"]
        or not result["root_readonly"]
        or result["forbidden_environment"]
        or not 0 < result["work_bytes"] <= 128 * 1024**2
        or with_input
        and not result["input_readonly"]
    ):
        raise ValueError("sandbox_requirements_not_met")
    return result


def probe(mode: str = "base") -> dict[str, Any]:
    result = require_sandbox(with_input=False)
    if mode == "memory":
        try:
            _ = bytearray(MEMORY_BYTES * 2)
        except MemoryError:
            result["memory_denied"] = True
        else:
            raise ValueError("memory_limit_not_enforced")
    elif mode == "disk":
        written = 0
        try:
            block = b"x" * (1024 * 1024)
            # Stay below per-file limits to exercise the aggregate tmpfs quota.
            for number in range(4):
                with Path(f"/work/disk-test-{number}").open("wb") as output:
                    for _ in range(48):
                        output.write(block)
                        written += len(block)
        except OSError:
            result["disk_denied"] = True
            result["written_bytes"] = written
        else:
            raise ValueError("disk_limit_not_enforced")
    elif mode == "network":
        denied = False
        try:
            with socket.create_connection(("1.1.1.1", 443), timeout=1):
                pass
        except OSError:
            denied = True
        result["network_denied"] = denied
        if not denied:
            raise ValueError("network_not_isolated")
    elif mode == "filesystem":
        for label, path in [("root", "/opt/worker/escape"), ("input", "/input/escape")]:
            if label == "input" and not Path("/input").exists():
                continue
            try:
                Path(path).write_text("not permitted")
            except OSError:
                result[label + "_write_denied"] = True
            else:
                raise ValueError("filesystem_not_readonly")
    elif mode == "pids":
        import time

        children = []
        try:
            for _ in range(64):
                try:
                    pid = os.fork()
                except OSError:
                    result["pids_denied"] = True
                    break
                if pid == 0:
                    time.sleep(8)
                    os._exit(0)
                children.append(pid)
            if not result.get("pids_denied"):
                raise ValueError("pid_limit_not_enforced")
            result["children_started"] = len(children)
        finally:
            import signal

            for pid in children:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
    elif mode == "cpu":
        resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
        while True:
            pass
    elif mode != "base":
        raise ValueError("unknown_probe")
    return result
