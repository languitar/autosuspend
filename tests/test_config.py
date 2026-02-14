import json

from autosuspend.config import (
    ConfigSchema,
    ParameterSchema,
    ParameterSchemaAware,
    ParameterType,
    config_param,
)


class TestConfigParam:
    def test_adds_schema(self) -> None:
        name = "baz"
        description = "This is a test parameter."
        default = 42

        @config_param(
            name=name,
            param_type=ParameterType.INTEGER,
            description=description,
            default=default,
            required=True,
        )
        class TestCheck(ParameterSchemaAware):
            pass

        assert TestCheck.config_parameters == [
            ParameterSchema(
                name=name,
                type=ParameterType.INTEGER,
                description=description,
                default=default,
                required=True,
            )
        ]

    def test_supports_multiple_params(self) -> None:
        @config_param(
            name="param1",
            param_type=ParameterType.STRING,
            description="First parameter.",
        )
        @config_param(
            name="param2",
            param_type=ParameterType.BOOLEAN,
            description="Second parameter.",
            default=True,
        )
        class TestCheck(ParameterSchemaAware):
            pass

        assert len(TestCheck.config_parameters) == 2


class TestConfigSchema:
    class TestToJson:
        def test_empty(self) -> None:
            assert json.loads(ConfigSchema().to_json()) == {
                "general_parameters": [],
                "activity_checks": {},
                "wakeup_checks": {},
            }

        def test_filled(self) -> None:
            schema = ConfigSchema(
                general_parameters=[
                    ParameterSchema(
                        name="global_param",
                        type=ParameterType.STRING,
                        description="A global parameter.",
                    )
                ],
                activity_checks={
                    "check1": [
                        ParameterSchema(
                            name="check1_param",
                            type=ParameterType.INTEGER,
                            description="A parameter for check1.",
                        )
                    ]
                },
                wakeup_checks={
                    "check2": [
                        ParameterSchema(
                            name="check2_param",
                            type=ParameterType.BOOLEAN,
                            description="A parameter for check2.",
                            default=False,
                        )
                    ]
                },
            )

            expected_json = {
                "general_parameters": [
                    {
                        "name": "global_param",
                        "type": "string",
                        "description": "A global parameter.",
                        "default": None,
                        "required": False,
                        "minimum": None,
                        "maximum": None,
                        "pattern": None,
                        "enum_values": None,
                    }
                ],
                "activity_checks": {
                    "check1": [
                        {
                            "name": "check1_param",
                            "type": "integer",
                            "description": "A parameter for check1.",
                            "default": None,
                            "required": False,
                            "minimum": None,
                            "maximum": None,
                            "pattern": None,
                            "enum_values": None,
                        }
                    ]
                },
                "wakeup_checks": {
                    "check2": [
                        {
                            "name": "check2_param",
                            "type": "boolean",
                            "description": "A parameter for check2.",
                            "default": False,
                            "required": False,
                            "minimum": None,
                            "maximum": None,
                            "pattern": None,
                            "enum_values": None,
                        }
                    ]
                },
            }

            assert json.loads(schema.to_json()) == expected_json
