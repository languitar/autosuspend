from autosuspend.util import logger_by_class, logger_by_class_instance


class DummyClass:
    pass


class TestLoggerByClass:

    def test_smoke(self) -> None:
        logger = logger_by_class(DummyClass)
        assert logger is not None
        assert logger.name == 'tests.test_util.DummyClass'

    def test_name(self) -> None:
        logger = logger_by_class(DummyClass, 'foo')
        assert logger is not None
        assert logger.name == 'tests.test_util.DummyClass.foo'


class TestLoggerByClassInstance:

    def test_smoke(self) -> None:
        logger = logger_by_class_instance(DummyClass())
        assert logger is not None
        assert logger.name == 'tests.test_util.DummyClass'

    def test_name(self) -> None:
        logger = logger_by_class_instance(DummyClass(), 'foo')
        assert logger is not None
        assert logger.name == 'tests.test_util.DummyClass.foo'
