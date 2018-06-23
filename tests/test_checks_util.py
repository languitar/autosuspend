import configparser

import pytest
import requests

from autosuspend.checks import (Activity,
                                ConfigurationError,
                                TemporaryCheckError)
from autosuspend.checks.util import CommandMixin, NetworkMixin, XPathMixin


class _CommandMixinSub(CommandMixin, Activity):

    def __init__(self, name, command):
        Activity.__init__(self, name)
        CommandMixin.__init__(self, command)

    def check(self):
        pass


class TestCommandMixin:

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


class TestNetworkMixin:

    def test_collect_missing_url(self):
        with pytest.raises(ConfigurationError,
                           match=r"^Lacks 'url'.*"):
            parser = configparser.ConfigParser()
            parser.read_string('[section]')
            NetworkMixin.collect_init_args(parser['section'])

    def test_collect_default_timeout(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url=nourl''')
        args = NetworkMixin.collect_init_args(parser['section'])
        assert args['timeout'] == 5

    def test_collect_timeout(self):
        parser = configparser.ConfigParser()
        parser.read_string('''[section]
                           url=nourl
                           timeout=42''')
        args = NetworkMixin.collect_init_args(parser['section'])
        assert args['timeout'] == 42

    def test_collect_invalid_timeout(self):
        with pytest.raises(ConfigurationError,
                           match=r"^Configuration error .*"):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               url=nourl
                               timeout=xx''')
            NetworkMixin.collect_init_args(parser['section'])

    def test_request(self, stub_server):
        address = stub_server.resource_address('xml_with_encoding.xml')
        reply = NetworkMixin(address, 5).request()
        assert reply is not None
        assert reply.status_code == 200

    def test_requests_exception(self, mocker):
        with pytest.raises(TemporaryCheckError):
            mock_method = mocker.patch('requests.Session.get')
            mock_method.side_effect = requests.exceptions.ReadTimeout()

            NetworkMixin('url', timeout=5).request()

    def test_smoke(self, stub_server):
        response = NetworkMixin(stub_server.resource_address('data.txt'),
                                timeout=5).request()
        assert response is not None
        assert response.text == 'iamhere\n'

    def test_exception_404(self, stub_server):
        with pytest.raises(TemporaryCheckError):
            NetworkMixin(stub_server.resource_address('doesnotexist'),
                         timeout=5).request()

    def test_authentication(self, stub_auth_server):
        NetworkMixin(stub_auth_server.resource_address('data.txt'),
                     5, username='user', password='pass').request()

    def test_invalid_authentication(self, stub_auth_server):
        with pytest.raises(TemporaryCheckError):
            NetworkMixin(stub_auth_server.resource_address('data.txt'),
                         5, username='userx', password='pass').request()

    def test_file_url(self):
        NetworkMixin('file://' + __file__, 5).request()


class _XPathMixinSub(XPathMixin, Activity):

    def __init__(self, name, **kwargs):
        Activity.__init__(self, name)
        XPathMixin.__init__(self, **kwargs)

    def check(self):
        pass


class TestXPathMixin:

    def test_smoke(self, stub_server):
        address = stub_server.resource_address('xml_with_encoding.xml')
        result = _XPathMixinSub(
            'foo', xpath='/b', url=address, timeout=5).evaluate()
        assert result is not None
        assert len(result) == 0

    def test_broken_xml(self, mocker):
        with pytest.raises(TemporaryCheckError):
            mock_reply = mocker.MagicMock()
            content_property = mocker.PropertyMock()
            type(mock_reply).content = content_property
            content_property.return_value = b"//broken"
            mocker.patch('requests.Session.get', return_value=mock_reply)

            _XPathMixinSub(
                'foo', xpath='/b', url='nourl', timeout=5).evaluate()

    def test_xml_with_encoding(self, mocker):
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = \
            b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<root></root>"""
        mocker.patch('requests.Session.get', return_value=mock_reply)

        _XPathMixinSub('foo', xpath='/b', url='nourl', timeout=5).evaluate()

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
                           match=r"^Lacks '" + entry + "'.*"):
            parser = configparser.ConfigParser()
            parser.read_string('''[section]
                               xpath=/valid
                               url=nourl''')
            del parser['section'][entry]
            _XPathMixinSub.create('name', parser['section'])
