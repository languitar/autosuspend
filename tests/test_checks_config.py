from configparser import ConfigParser, SectionProxy

import pytest

from autosuspend.checks.config import Configuration, ConfigurationError, Options


class TestConfiguration:
    def test_get_no_value(self) -> None:
        with pytest.raises(KeyError):
            Configuration()["doesntexist"]

    def test_roundtrip(self) -> None:
        name = "thename"
        value = "thevalue"
        assert Configuration().add(name, value).get(name) == value

    def test_overwrite(self) -> None:
        name = "thename"
        value = "thevalue"
        assert Configuration().add(name, 42).add(name, value).get(name) == value

    def test_roundtrip_get(self) -> None:
        name = "thename"
        value = "thevalue"
        assert Configuration().add(name, value)[name] == value

    def test_debug_str(self) -> None:
        name = "thename"
        value = "thevalue"
        config = Configuration().add(name, value)
        assert name in config.debug_str()
        assert value in config.debug_str()

    def test_redacting(self) -> None:
        name = "thename"
        value = "thevalue"
        config = Configuration().add(name, value, redact=True)
        assert name in config.debug_str()
        assert value not in config.debug_str()
        assert config.is_redacted(name)

    def test_use_as_kwargs(self, mocker) -> None:
        value1 = "test"
        value2 = 42
        config = Configuration().add("foo", value1).add("bar", value2)

        call_target = mocker.MagicMock()
        call_target(**config)

        call_target.assert_called_once_with(foo=value1, bar=value2)


class TestOptions:
    @staticmethod
    def section(section_contents: str) -> SectionProxy:
        sec_name = "test_section"
        parser = ConfigParser()
        parser.read_string(
            f"""
            [{sec_name}]
            {section_contents}
            """,
        )
        return parser[sec_name]

    def test_noop_parse(self) -> None:
        result = Options().parse(self.section(""))
        assert isinstance(result, Configuration)
        assert len(result) == 0

    def test_parse(self, mocker) -> None:
        name = "theopt"
        value = 42

        parse_mock = mocker.MagicMock()
        parse_mock.return_value = value

        section = self.section(f"{name} = {value}")

        result = Options().add_option(name, parse_mock).parse(section)

        assert result[name] == value
        assert len(result) == 1
        assert parse_mock.call_count == 1
        parse_mock.assert_called_once_with(name, section)

    def test_exception_unexpected_option(self) -> None:
        section = self.section("name = 42")
        with pytest.raises(ConfigurationError):
            Options().parse(section)

    def test_exception_missing_option(self, mocker) -> None:
        section = self.section("")
        with pytest.raises(ConfigurationError):
            Options().add_option("foo", mocker.MagicMock(), required=True).parse(
                section
            )

    def test_non_required_works(self, mocker) -> None:
        name = "theopt"
        value = 42

        parse_mock = mocker.MagicMock()
        parse_mock.return_value = value

        section = self.section("")

        assert Options().add_option(name, parse_mock).parse(section)[name] == value

    def test_exception_redact(self, mocker) -> None:
        name = "theopt"

        parse_mock = mocker.MagicMock()
        parse_mock.return_value = 42

        section = self.section(f"{name} = foo")

        assert (
            Options()
            .add_option(name, parse_mock, redact=True)
            .parse(section)
            .is_redacted(name)
        )

    def test_validator_called(self, mocker) -> None:
        parser = mocker.MagicMock()
        parser.return_value = 42
        validator = mocker.MagicMock()
        Options().add_option("foo", parser).add_validator(validator).parse(
            self.section("")
        )
        validator.assert_called_once()
        assert len(validator.call_args.args[0]) == 1
