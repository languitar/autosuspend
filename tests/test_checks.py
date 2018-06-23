from autosuspend.checks import Check


class TestCheck:

    class DummyCheck(Check):

        @classmethod
        def create(cls, name, config):
            pass

        def check(self):
            pass

    def test_name(self):
        name = 'test'
        assert self.DummyCheck(name).name == name

    def test_name_default(self):
        assert self.DummyCheck().name is not None

    def test_str(self):
        assert isinstance(str(self.DummyCheck('test')), str)
