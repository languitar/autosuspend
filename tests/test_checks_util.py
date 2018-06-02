import configparser
import os.path

import requests

import pytest

from autosuspend.checks import (Activity,
                                ConfigurationError,
                                TemporaryCheckError)
from autosuspend.checks.util import (CommandMixin,
                                     XPathMixin,
                                     list_logind_sessions)


class _CommandMixinSub(CommandMixin, Activity):

    def __init__(self, name, command):
        Activity.__init__(self, name)
        CommandMixin.__init__(self, command)


class TestCommandMixin(object):

    def test_create(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                              command = narf bla  ''')
        check = _CommandMixinSub.create('name', parser['section'])
        assert check._command == 'narf bla'

    def test_create_no_command(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]''')
        with pytest.raises(ConfigurationError):
            _CommandMixinSub.create('name', parser['section'])


class _XPathMixinSub(XPathMixin, Activity):

    def __init__(self, name, url, xpath, timeout):
        Activity.__init__(self, name)
        XPathMixin.__init__(self, url, xpath, timeout)


class TestXPathMixin(object):

    @pytest.mark.parametrize('stub_server',
                             [os.path.join(os.path.dirname(__file__),
                                           'test_data')],
                             indirect=True)
    def test_smoke(self, stub_server):
        address = 'http://localhost:{}/xml_with_encoding.xml'.format(
            stub_server.server_address[1])
        _XPathMixinSub('foo', '/b', address, 5).evaluate()

    def test_broken_xml(self, mocker):
        with pytest.raises(TemporaryCheckError):
            mock_reply = mocker.MagicMock()
            content_property = mocker.PropertyMock()
            type(mock_reply).content = content_property
            content_property.return_value = b"//broken"
            mocker.patch('requests.get', return_value=mock_reply)

            _XPathMixinSub('foo', '/b', 'nourl', 5).evaluate()

    def test_xml_with_encoding(self, mocker):
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = \
            b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<root></root>"""
        mocker.patch('requests.get', return_value=mock_reply)

        _XPathMixinSub('foo', '/b', 'nourl', 5).evaluate()

    def test_xpath_prevalidation(self):
        with pytest.raises(ConfigurationError,
                           match=r'^Invalid xpath.*'):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=|34/ad
                               url=nourl''')
            _XPathMixinSub.create('name', parser['section'])

    @pytest.mark.parametrize('entry,', ['xpath', 'url'])
    def test_missing_config_entry(self, entry):
        with pytest.raises(ConfigurationError,
                           match=r"^No '" + entry + "'.*"):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=/valid
                               url=nourl''')
            del parser['section'][entry]
            _XPathMixinSub.create('name', parser['section'])

    def test_create_default_timeout(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           xpath=/valid
                           url=nourl''')
        check = _XPathMixinSub.create('name', parser['section'])
        assert check._timeout == 5

    def test_create_timeout(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           xpath=/valid
                           url=nourl
                           timeout=42''')
        check = _XPathMixinSub.create('name', parser['section'])
        assert check._timeout == 42

    def test_create_invalid_timeout(self):
        with pytest.raises(ConfigurationError,
                           match=r"^Configuration error .*"):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=/valid
                               url=nourl
                               timeout=xx''')
            _XPathMixinSub.create('name', parser['section'])

    def test_requests_exception(self, mocker):
        with pytest.raises(TemporaryCheckError):
            mock_method = mocker.patch('requests.get')
            mock_method.side_effect = requests.exceptions.ReadTimeout()

            _XPathMixinSub('foo', '/a', 'asdf', 5).evaluate()


def test_list_logind_sessions():
    pytest.importorskip('dbus')

    assert list_logind_sessions() is not None
