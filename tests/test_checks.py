import configparser

from autosuspend.checks import Check, CheckConfiguration


class TestCheckConfiguration:
    def test_smoke(self) -> None:
        assert "XXX" in CheckConfiguration().add("foo", "XXX").debug_str()
        assert "foo" in CheckConfiguration().add("foo", "XXX").debug_str()

    def test_redact(self) -> None:
        assert "XXX" not in CheckConfiguration().add("foo", "XXX", True).debug_str()

    def test_mutliple(self) -> None:
        result = CheckConfiguration().add("foo", "bar").add("bla", "blubb").debug_str()
        assert "foo" in result
        assert "bar" in result
        assert "bla" in result
        assert "blubb" in result


CONFIG = CheckConfiguration().add("foo", "bar")


class TestCheck:
    class DummyCheck(Check):
        def _configure(self, config: configparser.SectionProxy) -> CheckConfiguration:
            return CONFIG

    def test_name(self) -> None:
        name = "test"
        assert self.DummyCheck(name).name == name

    def test_name_default(self) -> None:
        assert self.DummyCheck().name is not None

    def test_str(self) -> None:
        assert isinstance(str(self.DummyCheck("test")), str)

    def test_configure(self) -> None:
        check = self.DummyCheck()

        parser = configparser.ConfigParser()
        parser.read_string("[section]")
        check.configure(parser["section"])

        assert check.configuration == CONFIG
