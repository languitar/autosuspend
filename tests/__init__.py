import abc
from typing import Any


class CheckTest(abc.ABC):

    @abc.abstractmethod
    def create_instance(self, name: str) -> Any:
        pass

    def test_name_passing(self) -> None:
        name = 'checktestname'
        assert self.create_instance(name).name == name
