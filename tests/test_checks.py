import configparser

from autosuspend.checks import Activity, Check, ErrorBehavior


class DummyCheck(Check):
    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "DummyCheck":
        raise NotImplementedError()

    def check(self) -> str | None:
        pass


class DummyActivity(Activity):
    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "DummyActivity":
        raise NotImplementedError()

    def check(self) -> str | None:
        pass


class TestCheck:
    class TestName:
        def test_returns_the_provided_name(self) -> None:
            name = "test"
            assert DummyCheck(name).name == name

        def test_has_a_sensible_default(self) -> None:
            assert DummyCheck().name is not None

    def test_has_a_string_representation(self) -> None:
        assert isinstance(str(DummyCheck("test")), str)


class TestActivity:
    def test_error_behavior_defaults_to_active(self) -> None:
        assert DummyActivity("test").error_behavior == ErrorBehavior.ACTIVE
