import configparser
from typing import Optional

from autosuspend.checks import Check


class DummyCheck(Check):
    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy) -> "DummyCheck":
        raise NotImplementedError()

    def check(self) -> Optional[str]:
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
