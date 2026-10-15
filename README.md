# codex-usage

Read Codex subscription usage using the official app-server protocol. Requires
Python 3, Codex CLI on PATH, and an existing ChatGPT login in the same VM/user
environment. It does not start a conversation, model turn, or review.

```sh
./codex-usage
./codex-usage --json
./codex-usage --timeout 15
```

Install on another VM by copying `codex-usage` to a directory on PATH and making
it executable (`chmod +x codex-usage`). Only that one file is needed at runtime.
Run `python3 -m unittest -v test_usage.py` to run the offline protocol tests.

The process inherits `CODEX_HOME`, `TZ`, and the VM's locale environment. Reset
times use the VM's local timezone (including DST), never a fixed timezone.
Human-readable dates follow `LC_TIME`; JSON timestamps use ISO 8601 with an offset.

All returned quota buckets are reported, with separate primary/secondary windows
and remaining percentages. Missing limits fail explicitly rather than reporting
100% available. JSON is filtered to usage fields; authentication and raw server
errors are never printed. Failures return exit status 1, and requests time out
after 30 seconds by default. No extra Python packages or API keys are needed.

For Grok Bot, run this command before/after a substantial delegated Codex task.
Use `--json` to parse `limits[].windows[].remaining_percent` and `resets_at`.
Grok Bot must have this script and its own Codex login in the VM where it runs;
installing it on another server does not install it in Grok Bot's VM.

Protocol: https://learn.chatgpt.com/docs/app-server
