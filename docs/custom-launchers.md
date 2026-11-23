# Custom launchers

An integration can implement `WasmCoverageTarget[T]`, a callable that accepts
the coverage fixture and returns a context manager yielding `T`. Use
`wasm_coverage.launch(start)` inside that target to get guest coverage settings
and submit its snapshot.

```python
from collections.abc import Callable
from typing import TypeVar

from coverage_wasm import GuestCoverage

Result = TypeVar("Result")

def launch(
    self,
    start: Callable[[GuestCoverage | None], Result],
    *,
    source_aliases: dict[str, list[str]] | None = None,
) -> Result: ...
```

`start` receives `None` when coverage is disabled. With coverage enabled,
`GuestCoverage` supplies the test `context` and `coverage.py`'s `branch`,
`source`, `include`, and `omit` settings. Use those settings before running
the application and call `guest.save(snapshot)` with the native `coverage.py`
file bytes before the runtime or its output disappears.

`launch` returns the launcher's result. A one-shot launcher can return a
completed result after saving coverage. A server launcher can return a
context manager that saves coverage during exit, before shutting down the
server.

`source_aliases` supplies fallback host-to-guest paths for computing source
filters. `coverage.py`'s `[paths]` takes precedence and controls how snapshots
are combined. A launcher may also translate its snapshot's filenames before
saving, as the WASI adapter does with filesystem grants.
