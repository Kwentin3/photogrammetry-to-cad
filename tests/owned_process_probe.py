"""Linux acceptance probe for the actual remote_job.sh + subreaper boundary.

Run with the existing Linux Python, --repo CHECKOUT --output NEW_DIRECTORY.
Three ~15s cases: exiting parent, native timeout and explicit cancellation.
No provider commands. Retains evidence; its unrelated control is stopped last.
--resume-only runs the quick receipt/reuse checks in a fresh output directory.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "ppid": int(fields[1]), "start": int(fields[19]),
                "state": fields[0], "pgid": os.getpgid(pid)}
    except (OSError, ValueError, IndexError):
        return None


def write(path, data):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(temporary, path)


def await_condition(predicate, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError("Bounded fixture condition did not become true")


def read_receipt(job):
    files = list(job.glob("*.owned-process"))
    if not files:
        return None
    return dict(line.split("=", 1) for line in files[0].read_text().splitlines())


def actor(path):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    write(path, identity(os.getpid()))
    while True:
        time.sleep(0.1)


def spawn(mode, actor_file):
    subprocess.Popen([sys.executable, __file__, "actor", actor_file], start_new_session=True)
    await_condition(lambda: Path(actor_file).is_file())
    if mode == "orphan":
        return 0
    while True:
        time.sleep(0.1)


def resume_checks(repo, output):
    """Mutate real owned receipts/status; refusal must never execute the command."""
    job, counter = output / "resume-job", output / "resume-counter.txt"
    code = ("from pathlib import Path\nimport sys\np=Path(sys.argv[1])\n"
            "p.write_text(str(int(p.read_text())+1 if p.exists() else 1))\n")
    argv = ["bash", str(repo / "scripts/remote_job.sh"), str(job), "10",
            "--", sys.executable, "-c", code, str(counter)]
    fresh = subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=15)
    assert fresh.returncode == 0, fresh.stderr
    assert counter.read_text() == "1"
    resume = argv[:4] + ["--resume"] + argv[4:]
    status_file = job / "status"
    status = dict(line.split("=", 1) for line in status_file.read_text().splitlines())
    receipt_file = job / (Path(status["log"]).stem + ".owned-process")
    original_status, original_receipt = status_file.read_bytes(), receipt_file.read_bytes()
    results = []

    def invoke(label, accepted):
        before_files = {path.name for path in job.iterdir()}
        before_status = status_file.read_bytes()
        checked = subprocess.run(resume, cwd=repo, capture_output=True, text=True, timeout=10)
        if accepted:
            assert checked.returncode == 0 and "Existing successful job reused" in checked.stdout
        else:
            assert checked.returncode != 0 and "inspect" in checked.stderr.lower(), checked.stderr
        assert counter.read_text() == "1", "Resume unexpectedly executed a new command"
        assert {path.name for path in job.iterdir()} == before_files, "Resume started a new attempt"
        assert status_file.read_bytes() == before_status, "Resume overwrote prior state"
        results.append({"case": label, "returncode": checked.returncode,
                        "stdout": checked.stdout, "stderr": checked.stderr,
                        "command_execution_count": 1})

    try:
        invoke("reuse_confirmed", True)
        receipt_file.write_bytes(original_receipt.replace(b"cleanup=confirmed", b"cleanup=unknown"))
        invoke("refuse_unknown_receipt", False)
        receipt_file.unlink()
        invoke("refuse_missing_receipt", False)
        receipt_file.write_bytes(original_receipt)
        status_file.write_bytes(original_status.replace(b"state=succeeded", b"state=failed")
                                .replace(b"cleanup=confirmed", b"cleanup=unknown"))
        invoke("refuse_unknown_status_on_failed_resume", False)
    finally:
        receipt_file.write_bytes(original_receipt)
        status_file.write_bytes(original_status)
    assert receipt_file.read_bytes() == original_receipt and status_file.read_bytes() == original_status
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-only", action="store_true")
    args = parser.parse_args()
    assert sys.platform == "linux"
    args.repo = args.repo.resolve()
    output = args.output.resolve()
    if output == args.repo or args.repo in output.parents:
        raise ValueError("Probe evidence must stay outside the checkout")
    output.mkdir(parents=True, exist_ok=False)
    if args.resume_only:
        checks = resume_checks(args.repo, output)
        write(output / "result.json", {"status": "passed", "cases": [], "resume_checks": checks})
        print(json.dumps({"status": "passed", "resume_checks": len(checks), "output": str(output)}))
        return
    runner = args.repo.resolve() / "scripts/remote_job.sh"
    records = []
    control = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(100)"],
                               start_new_session=True)
    control_identity = identity(control.pid)
    try:
        for mode, expected in (("orphan", 0), ("timeout", 124), ("cancel", 143)):
            actor_file = output / (mode + "-actor.json")
            job = output / (mode + "-job")
            argv = ["bash", str(runner), str(job), "1" if mode == "timeout" else "45",
                    "--", sys.executable, __file__, "spawn", mode, str(actor_file)]
            with (output / (mode + ".launcher.log")).open("wb") as log:
                launch = subprocess.Popen(argv, cwd=args.repo, stdout=log, stderr=log,
                                          start_new_session=True)
                try:
                    await_condition(lambda: actor_file.is_file())
                    observed = json.loads(actor_file.read_text())
                    receipt = await_condition(lambda: read_receipt(job))
                    helper = int(receipt["subreaper_pid"])
                    group = int((job / "process_group").read_text())
                    assert observed["pgid"] != group, "Fixture did not exercise a native separate session"
                    assert identity(observed["pid"])["start"] == observed["start"]
                    assert control.poll() is None
                    if mode == "cancel":
                        launch.send_signal(signal.SIGTERM)
                    adopted = await_condition(lambda: (
                        value if (value := identity(observed["pid"])) and value["ppid"] == helper else None))
                    result = launch.wait(timeout=35)
                finally:
                    if launch.poll() is None:
                        launch.send_signal(signal.SIGTERM)
                        launch.wait(timeout=35)
            status = dict(line.split("=", 1) for line in (job / "status").read_text().splitlines())
            receipt = read_receipt(job)
            after = identity(observed["pid"])
            assert after is None or after["start"] != observed["start"], (mode, "Owned actor survived", after)
            assert result == expected, (mode, result, status)
            assert status["cleanup"] == "confirmed" and receipt["cleanup"] == "confirmed"
            assert status["state"] == {"orphan": "succeeded", "timeout": "timed_out",
                                       "cancel": "cancelled"}[mode]
            assert list(job.glob("*.owned-helper.sha256")), "Missing exact helper identity"
            assert control.poll() is None and identity(control.pid)["start"] == control_identity["start"]
            records.append({"case": mode, "returncode": result, "actor": observed,
                            "observed_adoption": adopted, "after": after, "status": status,
                            "helper_receipt": receipt, "command_sha256": (job / "command.sha256").read_text().strip()})
            write(output / "result.json", {"status": "running", "cases": records,
                                          "unrelated_control": control_identity})
        checks = resume_checks(args.repo, output)
        write(output / "result.json", {"status": "passed", "cases": records, "resume_checks": checks,
                                      "unrelated_control_survived_all_cases": control_identity})
        print(json.dumps({"status": "passed", "cases": len(records), "output": str(output)}))
    finally:
        if control.poll() is None:
            control.terminate()
        control.wait(timeout=5)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "actor":
        actor(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "spawn":
        sys.exit(spawn(sys.argv[2], sys.argv[3]))
    else:
        main()
