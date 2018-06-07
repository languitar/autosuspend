import configparser
from typing import Any, Dict, Iterable

from .. import ConfigurationError, TemporaryCheckError


class CommandMixin(object):
    """Mixin for configuring checks based on external commands."""

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy):
        try:
            return cls(name, config['command'].strip())  # type: ignore
        except KeyError:
            raise ConfigurationError('Missing command specification')

    def __init__(self, command: str) -> None:
        self._command = command


class NetworkMixin(object):

    @classmethod
    def collect_init_args(
            cls, config: configparser.SectionProxy) -> Dict[str, Any]:
        try:
            args = {}  # type: Dict[str, Any]
            args['timeout'] = config.getint('timeout', fallback=5)
            args['url'] = config['url']
            return args
        except ValueError as error:
            raise ConfigurationError('Configuration error ' + str(error))
        except KeyError as error:
            raise ConfigurationError('Lacks ' + str(error) + ' config entry')

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy):
        return cls(name, **cls.collect_init_args(config))  # type: ignore

    def __init__(self, url: str, timeout: int) -> None:
        self._url = url
        self._timeout = timeout

    def request(self):
        import requests
        import requests.exceptions

        try:
            reply = requests.get(self._url, timeout=self._timeout)
            reply.raise_for_status()
            return reply
        except requests.exceptions.RequestException as error:
            raise TemporaryCheckError(error)


class XPathMixin(NetworkMixin):

    @classmethod
    def collect_init_args(cls, config) -> Dict[str, Any]:
        from lxml import etree
        try:
            args = NetworkMixin.collect_init_args(config)
            args['xpath'] = config['xpath'].strip()
            # validate the expression
            try:
                etree.fromstring('<a></a>').xpath(args['xpath'])
            except etree.XPathEvalError:
                raise ConfigurationError(
                    'Invalid xpath expression: ' + args['xpath'])
            return args
        except ValueError as error:
            raise ConfigurationError('Configuration error ' + str(error))
        except KeyError as error:
            raise ConfigurationError(
                'Lacks ' + str(error) + ' config entry')

    @classmethod
    def create(cls, name: str, config: configparser.SectionProxy):
        return cls(name, **cls.collect_init_args(config))

    def __init__(self, xpath: str, url: str, timeout: int) -> None:
        NetworkMixin.__init__(self, url, timeout)
        self._xpath = xpath

    def evaluate(self) -> Iterable[Any]:
        import requests
        import requests.exceptions
        from lxml import etree

        try:
            reply = self.request().content
            root = etree.fromstring(reply)
            return root.xpath(self._xpath)
        except requests.exceptions.RequestException as error:
            raise TemporaryCheckError(error)
        except etree.XMLSyntaxError as error:
            raise TemporaryCheckError(error)
