from atexit import register
from importlib.util import find_spec
from os import environ
from pathlib import Path

from coverage import Coverage


def measure_package(data_file: str) -> None:
    package = find_spec("coverage_wasm")
    if package is None or package.origin is None:
        return
    coverage = Coverage(
        config_file=False,
        source=[str(Path(package.origin).parent)],
        branch=True,
        data_file=data_file,
        data_suffix=True,
    )
    coverage.set_option("run:core", "sysmon")
    coverage.set_option("run:disable_warnings", ["no-data-collected"])
    coverage.start()
    collector = coverage._collector  # pyright: ignore[reportPrivateUsage]
    assert collector is not None
    collectors = collector._collectors  # pyright: ignore[reportPrivateUsage]
    instances = coverage._instances  # pyright: ignore[reportPrivateUsage]

    # Keep the audit's sys.monitoring tool independent of the pytest-cov
    # collector stack. Nested consumer runs see the usual ctrace collector.
    collectors.remove(collector)
    instances.remove(coverage)
    environ["COVERAGE_CORE"] = "ctrace"

    @register
    def save_package_coverage() -> None:
        collectors.append(collector)
        instances.append(coverage)
        coverage.stop()
        coverage.save()


if (data_file := environ.get("WASM_PACKAGE_COVERAGE")) is not None:
    measure_package(data_file)
