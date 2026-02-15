import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, ClassVar


class ParameterType(Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "number"
    BOOLEAN = "boolean"
    STRING_LIST = "array"


@dataclass
class ParameterSchema:
    """Describes the configuration schema of a single config parameter."""

    name: str
    type: ParameterType
    description: str
    default: Any = None
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    enum_values: list | None = None


class ParameterSchemaAware:
    """Mixin for classes that are aware of their parameter schema."""

    config_parameters: ClassVar[list[ParameterSchema]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # inherit config parameters from parent classes to avoid having to repeat them
        # for every subclass of a mixin etc.
        inherited_params: list[ParameterSchema] = []
        for base in cls.__mro__[1:]:  # Skip self, start from first parent
            if hasattr(base, "config_parameters") and base.config_parameters:
                # add parameters from this base class that aren't already present. This
                # allows overriding them if required.
                for param in base.config_parameters:
                    if not any(p.name == param.name for p in inherited_params):
                        inherited_params.append(param)
        cls.config_parameters = inherited_params.copy()


def config_param(
    name: str,
    param_type: ParameterType,
    description: str,
    default: Any = None,
    required: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
    pattern: str | None = None,
    enum_values: list | None = None,
) -> Callable[[type[ParameterSchemaAware]], type[ParameterSchemaAware]]:
    """Decorates a check class with the description of a single configuration parameter."""

    def decorator(cls: type[ParameterSchemaAware]) -> type[ParameterSchemaAware]:
        # Check if parameter with this name already exists and remove it
        cls.config_parameters = [p for p in cls.config_parameters if p.name != name]
        # Add the new parameter
        cls.config_parameters.append(
            ParameterSchema(
                name,
                param_type,
                description,
                default,
                required,
                minimum,
                maximum,
                pattern,
                enum_values,
            )
        )
        return cls

    return decorator


def _remove_none_values(data: Any) -> Any:
    """Recursively remove None values from dictionaries."""
    if isinstance(data, dict):
        return {k: _remove_none_values(v) for k, v in data.items() if v is not None}
    elif isinstance(data, list):
        return [_remove_none_values(item) for item in data]
    return data


class ConfigEncoder(json.JSONEncoder):
    """Custom JSON encoder that can handle ParameterType enums."""

    def default(self, o: Any) -> Any:
        if isinstance(o, ParameterType):
            return o.value
        return super().default(o)


@dataclass
class ConfigSchema:
    """Describes the overall configuration schema for the autosuspend system.

    Attributes:
        global_parameters: parameters for the [global] section
        activity_checks: mapping of activity check class names to their parameters
        wakeup_checks: mapping of wakeup check class names to their parameters
    """

    general_parameters: list[ParameterSchema] = field(default_factory=list)
    activity_checks: dict[str, list[ParameterSchema]] = field(default_factory=dict)
    wakeup_checks: dict[str, list[ParameterSchema]] = field(default_factory=dict)

    def to_json(self) -> str:
        data = asdict(self)
        data = _remove_none_values(data)
        return json.dumps(data, indent=2, cls=ConfigEncoder)


GENERAL_PARAMETERS = [
    ParameterSchema(
        name="interval",
        type=ParameterType.INTEGER,
        description="The time to wait after executing all checks in seconds.",
        required=True,
        minimum=1,
    ),
    ParameterSchema(
        name="idle_time",
        type=ParameterType.INTEGER,
        description="The required amount of time in seconds with no detected activity before the host will be suspended.",
        default=300,
        minimum=1,
    ),
    ParameterSchema(
        name="min_sleep_time",
        type=ParameterType.INTEGER,
        description="The minimal amount of time in seconds the system has to sleep for actually triggering suspension. If a scheduled wake up results in an effective time below this value, the system will not sleep.",
        default=1200,
        minimum=0,
    ),
    ParameterSchema(
        name="wakeup_delta",
        type=ParameterType.INTEGER,
        description="Wake up the system this amount of seconds earlier than the time that was determined for an event that requires the system to be up. This value adds a safety margin for the time a the wake up effectively takes.",
        default=30,
        minimum=0,
    ),
    ParameterSchema(
        name="suspend_cmd",
        type=ParameterType.STRING,
        description="The command to execute in case the host shall be suspended. This line can contain additional command line arguments to the command to execute.",
        required=True,
    ),
    ParameterSchema(
        name="wakeup_cmd",
        type=ParameterType.STRING,
        description="The command to execute for scheduling a wake up of the system. The given string is processed using Python's str.format and a format argument called 'timestamp' encodes the UTC timestamp of the planned wake up time (float). Additionally 'iso' can be used to acquire the timestamp in ISO 8601 format.",
    ),
    ParameterSchema(
        name="notify_cmd_wakeup",
        type=ParameterType.STRING,
        description="A command to execute before the system is going to suspend for the purpose of notifying interested clients. This command is only called in case a wake up is scheduled. The given string is processed using Python's str.format and a format argument called 'timestamp' encodes the UTC timestamp of the planned wake up time (float). Additionally 'iso' can be used to acquire the timestamp in ISO 8601 format. If empty or not specified, no command will be called.",
    ),
    ParameterSchema(
        name="notify_cmd_no_wakeup",
        type=ParameterType.STRING,
        description="A command to execute before the system is going to suspend for the purpose of notifying interested clients. This command is only called in case NO wake up is scheduled. Hence, no string formatting options are available. If empty or not specified, no command will be called.",
    ),
]
