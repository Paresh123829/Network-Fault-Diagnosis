from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def normalize_timestamp(timestamp_utc: Optional[datetime], raw_timestamp_str: Optional[Any]) -> datetime:
    """
    Ensures a valid UTC datetime.
    Prefers timestamp_utc if present. Otherwise, attempts to parse raw_timestamp_str.
    Supports Unix seconds, milliseconds, microseconds, and nanoseconds, as well as Cisco syslogs.
    If both are None or unparseable, raises a ValueError.
    """
    if timestamp_utc:
        # Ensure it has timezone info
        if timestamp_utc.tzinfo is None:
            return timestamp_utc.replace(tzinfo=timezone.utc)
        return timestamp_utc.astimezone(timezone.utc)

    if raw_timestamp_str is not None:
        raw_str = str(raw_timestamp_str).strip()
        if raw_str:
            # 1. Try ISO 8601 string (e.g. Case 12: 2020-02-06 19:41:25.409000+00:00)
            if "T" in raw_str or ("-" in raw_str and ":" in raw_str):
                try:
                    dt = datetime.fromisoformat(raw_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc)
                except ValueError:
                    pass

            # 2. Try numeric epoch (seconds, ms, us, ns)
            try:
                val = float(raw_str)
                if val == 0:
                    return datetime(1970, 1, 1, 0, 0, tzinfo=timezone.utc)
                if 0 < val < 1e21:
                    if val < 1e11:
                        sec = val
                    elif val < 1e14:
                        sec = val / 1e3
                    elif val < 1e17:
                        sec = val / 1e6
                    else:
                        sec = val / 1e9

                    # Windows platform-safe range check (1970 to ~year 3000)
                    if 0 <= sec <= 32535215999:
                        return datetime.fromtimestamp(sec, tz=timezone.utc)
            except (ValueError, OverflowError, OSError, TypeError):
                pass

            # 3. Try Cisco IOS-XR syslog format: 'Aug  4 10:19:44.199'
            clean_ts = raw_str.replace("  ", " ")
            DEFAULT_YEAR = 2018
            for fmt in ("%Y %b %d %H:%M:%S.%f", "%Y %b %d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(f"{DEFAULT_YEAR} {clean_ts}", fmt)
                    return parsed.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue

    raise ValueError(f"Cannot normalize timestamp: unparseable or missing ({raw_timestamp_str})")


def normalize_device_id(device_id: str) -> str:
    """
    Normalizes a device identifier (e.g. lowercase, strips whitespace).
    """
    return device_id.strip().lower()


def normalize_interface(interface: Optional[str]) -> Optional[str]:
    """
    Normalizes an interface name.
    E.g. expands abbreviations like 'Hu' to 'HundredGigE', strips whitespace.
    """
    if not interface:
        return None
        
    interface = interface.strip()
    
    # Common abbreviations in Cisco logs
    lower_if = interface.lower()
    if lower_if.startswith("hu") and not lower_if.startswith("hundredgige"):
        # e.g., Hu0/0/0/16 -> HundredGigE0/0/0/16
        return "HundredGigE" + interface[2:]
    if lower_if.startswith("gi") and not lower_if.startswith("gigabitethernet"):
        return "GigabitEthernet" + interface[2:]
        
    return interface


def sanitize_string(text: Optional[str]) -> Optional[str]:
    """
    Removes potentially dangerous control characters while preserving formatting.
    """
    if not text:
        return text
    # Keep printable characters, spaces, tabs, and newlines.
    return "".join(char for char in text if char.isprintable() or char in ("\n", "\t"))
