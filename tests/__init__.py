import abc

from autosuspend.checks import Check


class CheckTest(abc.ABC):
    @abc.abstractmethod
    def create_instance(self, name: str) -> Check:
        pass

    def test_name_passing(self) -> None:
        name = "checktestname"
        assert self.create_instance(name).name == name
