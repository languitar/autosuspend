from collections.abc import Mapping
import configparser
from typing import Optional


def config_section(
    entries: Optional[Mapping[str, str]] = None
) -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    section_name = "a_section"
    parser.read_dict({section_name: entries or {}})
    return parser[section_name]
