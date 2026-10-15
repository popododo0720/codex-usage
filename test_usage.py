"""Protocol integration tests with a fake Codex process; no account required."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("codex-usage")
FAKE = r'''#!/usr/bin/env python3
import json, os, sys, time
assert sys.argv[1:] == ["app-server", "--listen", "stdio://"]
mode = os.environ.get("FAKE_MODE", "normal")
with open(os.environ["FAKE_PID"], "w") as f:
    f.write(str(os.getpid()))
init = json.loads(input())
assert init["method"] == "initialize"
print(json.dumps({"id": init["id"], "result": {}}), flush=True)
assert json.loads(input())["method"] == "initialized"
request = json.loads(input())
assert request["method"] == "account/rateLimits/read"
if mode == "timeout":
    time.sleep(60)
elif mode == "error":
    print(json.dumps({"id": request["id"], "error": {"message": "SECRET_DO_NOT_PRINT"}}), flush=True)
elif mode == "eof":
    sys.exit(0)
else:
    bucket = {"limitId": "codex", "planType": "plus", "primary": {
        "usedPercent": 25, "windowDurationMins": 300, "resetsAt": 0},
        "secondary": {"usedPercent": 80, "windowDurationMins": 10080, "resetsAt": 0}}
    if mode == "empty":
        result = {"rateLimits": None}
    elif mode == "legacy":
        result = {"rateLimits": bucket}
    else:
        result = {"rateLimitsByLimitId": {"codex": bucket,
            "other": {"limitId": "other", "primary": {"usedPercent": 100}}}}
    if os.environ.get("FAKE_RESET"):
        bucket["primary"]["resetsAt"] = int(os.environ["FAKE_RESET"])
    result["accessToken"] = "SECRET_DO_NOT_PRINT"
    print(json.dumps({"method": "some/notification"}), flush=True)
    print(json.dumps({"id": request["id"], "result": result}), flush=True)
time.sleep(60)  # Client must terminate the process after receiving a response.
'''


class ProtocolTests(unittest.TestCase):
    def run_client(self, mode="normal", timezone="UTC", reset="0"):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp, "codex")
            fake.write_text(FAKE)
            fake.chmod(0o755)
            pid_file = Path(tmp, "pid")
            env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"],
                       FAKE_MODE=mode, FAKE_PID=str(pid_file), FAKE_RESET=reset,
                       TZ=timezone, LC_TIME="C")
            result = subprocess.run(
                [str(SCRIPT), "--json", "--timeout", "0.5"],
                env=env, text=True, capture_output=True, timeout=5,
            )
            self.assertNotIn("SECRET_DO_NOT_PRINT", result.stdout + result.stderr)
            if pid_file.exists():
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid_file.read_text()), 0)
            return result

    def test_handshake_multiple_buckets_and_unknown_reset(self):
        result = self.run_client()
        self.assertEqual(result.returncode, 0, result.stderr)
        limits = json.loads(result.stdout)["limits"]
        self.assertEqual(len(limits), 2)
        self.assertEqual([w["remaining_percent"] for w in limits[0]["windows"]], [75, 20])
        self.assertEqual(limits[1]["windows"][0]["remaining_percent"], 0)
        self.assertIsNone(limits[1]["windows"][0]["resets_at"])

    def test_vm_timezone_including_dst(self):
        for timezone, expected in [("UTC", "1970-01-01T00:00:00+00:00"),
                                   ("America/New_York", "1969-12-31T19:00:00-05:00")]:
            with self.subTest(timezone=timezone):
                result = self.run_client(timezone=timezone)
                self.assertEqual(result.returncode, 0, result.stderr)
                window = json.loads(result.stdout)["limits"][0]["windows"][0]
                self.assertEqual(window["resets_at"], expected)
                self.assertIn("1970" if timezone == "UTC" else "1969", window["resets_at_local"])
        result = self.run_client(timezone="America/New_York", reset="1782864000")
        self.assertEqual(result.returncode, 0, result.stderr)
        window = json.loads(result.stdout)["limits"][0]["windows"][0]
        self.assertEqual(window["resets_at"], "2026-06-30T20:00:00-04:00")

    def test_legacy_bucket(self):
        result = self.run_client("legacy")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["limits"]), 1)

    def test_no_limits_is_not_reported_as_full_quota(self):
        result = self.run_client("empty")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("No subscription limit", result.stderr)

    def test_rpc_error_is_redacted(self):
        result = self.run_client("error")
        self.assertEqual(result.returncode, 1)
        self.assertIn("login", result.stderr)

    def test_timeout_and_cleanup(self):
        result = self.run_client("timeout")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Timed out", result.stderr)

    def test_early_exit(self):
        result = self.run_client("eof")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exited", result.stderr)


if __name__ == "__main__":
    unittest.main()
