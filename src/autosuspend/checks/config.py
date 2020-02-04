"""Minimalistic configuration system for checks based on configparser."""

from collections import Mapping
import configparser
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List


class ConfigurationError(RuntimeError):
    """Indicates an error in the configuration of a :class:`Check`."""

    pass


@dataclass
class _ConfigValue:
    name: str
    value: Any
    redact: bool = False


class Configuration(Mapping):
    """Representation of parsed configuration values for a check type."""

    def __init__(self) -> None:
        self.config_values: Dict[str, _ConfigValue] = {}

    def add(self, name: str, value: Any, redact: bool = False) -> "Configuration":
        self.config_values[name] = _ConfigValue(name, value, redact)
        return self

    def __getitem__(self, name: str) -> Any:
        return self.config_values[name].value

    def __len__(self) -> int:
        return len(self.config_values)

    def __iter__(self) -> Iterator[str]:
        return self.config_values.__iter__()

    def is_redacted(self, name: str) -> bool:
        return self.config_values[name].redact

    def debug_str(self) -> str:
        as_dict = {
            v.name: v.value if not v.redact else "<redacted>"
            for v in self.config_values.values()
        }
        return str(as_dict)


ParserFunc = Callable[[str, configparser.SectionProxy], Any]
ValidatorFunc = Callable[[Configuration], None]


@dataclass
class _OptionConfig:
    parser: ParserFunc
    required: bool = False
    redact: bool = False


class Options:
    """Declaration of config options of a single check."""

    def __init__(self) -> None:
        self.options: Dict[str, _OptionConfig] = {}
        self.validators: List[ValidatorFunc] = []

    def add_option(
        self,
        name: str,
        parser: ParserFunc,
        required: bool = False,
        redact: bool = False,
    ) -> "Options":
        self.options[name] = _OptionConfig(
            parser=parser, required=required, redact=redact
        )
        return self

    def add_validator(self, validator: ValidatorFunc) -> "Options":
        self.validators.append(validator)
        return self

    def parse(self, config: configparser.SectionProxy) -> Configuration:
        if set(config.keys()) > set(self.options.keys()):
            raise ConfigurationError(
                "Additional configuration keys "
                f"{set(self.options.keys()) - set(config.keys())} "
                "not supported by this check."
            )

        result = Configuration()
        for name, option in self.options.items():
            if name not in config and option.required:
                raise ConfigurationError(f"Option {name} is missing")
            result.add(
                name, option.parser(name, config), redact=option.redact,
            )

        for validator in self.validators:
            validator(result)

        return result
