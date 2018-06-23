import abc


class CheckTest(abc.ABC):

    @abc.abstractmethod
    def create_instance(self, name):
        pass

    def test_name_passing(self):
        name = 'checktestname'
        assert self.create_instance(name).name == name
