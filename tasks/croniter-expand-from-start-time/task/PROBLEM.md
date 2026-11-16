# `expand_from_start_time=True` doesn't do what the documentation says

We schedule jobs with croniter and use `expand_from_start_time=True`, so that a
step like `*/15` counts from the job's start time instead of from minute 0.

Our office-hours job is meant to run every minute between 08:00 and 17:59:

```python
from datetime import datetime
from croniter import croniter

start = datetime(2026, 1, 1, 7, 7)
it = croniter("* 8-17 * * *", start, expand_from_start_time=True)
print(it.expanded[1])
```

We expect hours `8` to `17`. We get `[0, 1, 2, …, 17]`, so the job also runs
in the middle of the night.

The README (the section on `expand_from_start_time`) and the 7.0 notes in
`CHANGELOG.rst` describe exactly how the flag is supposed to behave. We
compared a few more of our schedules with that description and they don't
match either. We think the implementation simply doesn't follow its own
documentation, and probably in more than one place.

## What we expect

- With `expand_from_start_time=True`, croniter behaves the way the README
  section on `expand_from_start_time` and the 7.0 notes in `CHANGELOG.rst`
  describe, for every field: minutes, hours, day of month, month, day of week,
  and the optional seconds and years fields. This includes any start time,
  naive or timezone-aware.
- Without the flag, nothing changes.
- The existing test suite keeps passing: `python -m pytest src` from the root
  of the repository.

The documentation is the specification here. Where it says how something
behaves, the code should do that.

## Constraints

- No new dependencies.
- Don't change the documentation to match the code.
