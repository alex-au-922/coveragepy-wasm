from pathlib import Path

from coverage import Coverage


def snapshot(collector: Coverage) -> bytes:
    """Save the collector and return the native .coverage file."""
    collector.save()
    return Path(collector.get_data().data_filename()).read_bytes()
