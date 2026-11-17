# Status

This file is a stable pointer and is hand-written. The status is not committed, because a committed copy conflicted on almost every merge.

Get the current gate, what is built, what is ready to start and the latest logs:

```bash
python3 scripts/build_status.py
```

`python3 scripts/session_start.py` prints a shorter orientation. CI shows the same status in each run summary. The "Ready to start" list in the output replaces the old "Ready to start" section of this file; the plan itself is [PLAN.md](PLAN.md).
