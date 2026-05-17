"""Arc directory-name parsing helpers matching legacy FMC Combine_data behavior."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ArcInfo:
    """Parsed legacy arc directory metadata."""

    arc_name: str
    cell_name: str
    output_pin: str
    output_pin_direction: str
    rel_pin: str
    rel_pin_direction: str
    when: str
    first_index: str
    sec_index: str


def normalize_arc_name(arc_dir_name: str) -> str:
    """Normalize an arc directory name the same way legacy calculate.py does."""

    return re.sub(r"(\d)-(\d)", r"\1_\2", arc_dir_name)


def parse_arc_info(arc_dir_name: str) -> ArcInfo:
    """Parse a legacy FMC arc directory name.

    The minimum-pulse-width form keeps the legacy special case where
    ``min_pulse_width`` consumes three leading tokens but only ``min``/``pulse``
    are used to detect the format.
    """

    arc_name = normalize_arc_name(arc_dir_name)
    parts = arc_name.split("_")

    if len(parts) >= 2 and parts[0] == "min" and parts[1] == "pulse":
        cell_name = parts[3]
        output_pin = parts[4]
        output_pin_direction = parts[5]
        rel_pin = parts[6]
        rel_pin_direction = parts[7]
        when_condition = parts[8:][:-3]
        first_index = parts[-3]
        sec_index = parts[-2]
    else:
        cell_name = parts[1]
        output_pin = parts[2]
        output_pin_direction = parts[3]
        rel_pin = parts[4]
        rel_pin_direction = parts[5]
        when_condition = parts[6:][:-2]
        first_index = parts[-2]
        sec_index = parts[-1]

    if len(when_condition) > 1 and when_condition[0] == "NO" and when_condition[1] == "CONDITION":
        when = "None"
    else:
        when = "&".join(item.replace("not", "!") for item in when_condition)

    return ArcInfo(
        arc_name=arc_name,
        cell_name=cell_name,
        output_pin=output_pin,
        output_pin_direction=output_pin_direction,
        rel_pin=rel_pin,
        rel_pin_direction=rel_pin_direction,
        when=when,
        first_index=first_index,
        sec_index=sec_index,
    )
