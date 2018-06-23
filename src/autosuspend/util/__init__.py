import logging


def logger_by_class(klass, name=None):
    return logging.getLogger(
        '{module}.{klass}{name}'.format(
            module=klass.__module__,
            klass=klass.__name__,
            name='.{}'.format(name) if name else ''))


def logger_by_class_instance(instance, name=None):
    return logger_by_class(instance.__class__, name=name)
