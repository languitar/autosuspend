import configparser
from collections.abc import Mapping


def config_section(
    entries: Mapping[str, str] | None = None,
) -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    section_name = "a_section"
    parser.read_dict({section_name: entries or {}})
    return parser[section_name]
