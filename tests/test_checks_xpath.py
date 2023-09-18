from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import pytest
from pytest_mock import MockerFixture

from autosuspend.checks import Activity, Check, ConfigurationError, TemporaryCheckError
from autosuspend.checks.xpath import (
    XPathActivity,
    XPathDeltaWakeup,
    XPathMixin,
    XPathWakeup,
)

from . import CheckTest
from .utils import config_section


class _XPathMixinSub(XPathMixin, Activity):
    def __init__(self, name: str, **kwargs: Any) -> None:
        Activity.__init__(self, name)
        XPathMixin.__init__(self, **kwargs)

    def check(self) -> Optional[str]:
        pass


class TestXPathMixin:
    def test_smoke(self, datadir: Path, serve_file: Callable[[Path], str]) -> None:
        result = _XPathMixinSub(
            "foo",
            xpath="/b",
            url=serve_file(datadir / "xml_with_encoding.xml"),
            timeout=5,
        ).evaluate()
        assert result is not None
        assert len(result) == 0

    def test_broken_xml(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = b"//broken"
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            _XPathMixinSub("foo", xpath="/b", url="nourl", timeout=5).evaluate()

    def test_xml_with_encoding(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = (
            b'<?xml version="1.0" encoding="ISO-8859-1" ?><root></root>'
        )
        mocker.patch("requests.Session.get", return_value=mock_reply)

        _XPathMixinSub("foo", xpath="/b", url="nourl", timeout=5).evaluate()

    def test_xpath_prevalidation(self) -> None:
        with pytest.raises(ConfigurationError, match=r"^Invalid xpath.*"):
            _XPathMixinSub.create(
                "name", config_section({"xpath": "|34/ad", "url": "required"})
            )

    @pytest.mark.parametrize("entry", ["xpath", "url"])
    def test_missing_config_entry(self, entry: str) -> None:
        section = config_section({"xpath": "/valid", "url": "required"})
        del section[entry]
        with pytest.raises(ConfigurationError, match=r"^Lacks '" + entry + "'.*"):
            _XPathMixinSub.create("name", section)

    def test_invalid_config_entry(self) -> None:
        with pytest.raises(ConfigurationError, match=r"^Configuration error .*"):
            _XPathMixinSub.create(
                "name",
                config_section(
                    {"xpath": "/valid", "url": "required", "timeout": "xxx"}
                ),
            )


class TestXPathActivity(CheckTest):
    def create_instance(self, name: str) -> Check:
        return XPathActivity(
            name=name,
            url="url",
            timeout=5,
            username="userx",
            password="pass",
            xpath="/b",
        )

    def test_matching(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mock_method = mocker.patch("requests.Session.get", return_value=mock_reply)

        url = "nourl"
        assert XPathActivity("foo", xpath="/a", url=url, timeout=5).check() is not None

        mock_method.assert_called_once_with(url, timeout=5, headers=None)
        content_property.assert_called_once_with()

    def test_not_matching(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert XPathActivity("foo", xpath="/b", url="nourl", timeout=5).check() is None

    def test_create(self) -> None:
        check: XPathActivity = XPathActivity.create(
            "name",
            config_section(
                {
                    "url": "url",
                    "xpath": "/xpath",
                    "username": "user",
                    "password": "pass",
                    "timeout": "42",
                }
            ),
        )  # type: ignore
        assert check._xpath == "/xpath"
        assert check._url == "url"
        assert check._username == "user"
        assert check._password == "pass"
        assert check._timeout == 42

    def test_network_errors_are_passed(
        self, datadir: Path, serve_protected: Callable[[Path], tuple[str, str, str]]
    ) -> None:
        with pytest.raises(TemporaryCheckError):
            XPathActivity(
                name="name",
                url=serve_protected(datadir / "data.txt")[0],
                timeout=5,
                username="wrong",
                password="wrong",
                xpath="/b",
            ).request()


class TestXPathWakeup(CheckTest):
    def create_instance(self, name: str) -> Check:
        return XPathWakeup(name, xpath="/a", url="nourl", timeout=5)

    def test_matching(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '<a value="42.3"></a>'
        mock_method = mocker.patch("requests.Session.get", return_value=mock_reply)

        url = "nourl"
        assert XPathWakeup("foo", xpath="/a/@value", url=url, timeout=5).check(
            datetime.now(timezone.utc)
        ) == datetime.fromtimestamp(42.3, timezone.utc)

        mock_method.assert_called_once_with(url, timeout=5, headers=None)
        content_property.assert_called_once_with()

    def test_not_matching(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert (
            XPathWakeup("foo", xpath="/b", url="nourl", timeout=5).check(
                datetime.now(timezone.utc)
            )
            is None
        )

    def test_not_a_string(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = "<a></a>"
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            XPathWakeup("foo", xpath="/a", url="nourl", timeout=5).check(
                datetime.now(timezone.utc)
            )

    def test_not_a_number(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '<a value="narf"></a>'
        mocker.patch("requests.Session.get", return_value=mock_reply)

        with pytest.raises(TemporaryCheckError):
            XPathWakeup("foo", xpath="/a/@value", url="nourl", timeout=5).check(
                datetime.now(timezone.utc)
            )

    def test_multiple_min(self, mocker: MockerFixture) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = """
            <root>
                <a value="40"></a>
                <a value="10"></a>
                <a value="20"></a>
            </root>
        """
        mocker.patch("requests.Session.get", return_value=mock_reply)

        assert XPathWakeup("foo", xpath="//a/@value", url="nourl", timeout=5).check(
            datetime.now(timezone.utc)
        ) == datetime.fromtimestamp(10, timezone.utc)

    def test_create(self) -> None:
        check: XPathWakeup = XPathWakeup.create(
            "name",
            config_section(
                {
                    "xpath": "/valid",
                    "url": "nourl",
                    "timeout": "20",
                }
            ),
        )  # type: ignore
        assert check._xpath == "/valid"


class TestXPathDeltaWakeup(CheckTest):
    def create_instance(self, name: str) -> Check:
        return XPathDeltaWakeup(name, xpath="/a", url="nourl", timeout=5, unit="days")

    @pytest.mark.parametrize(
        ("unit", "factor"),
        [
            ("microseconds", 0.000001),
            ("milliseconds", 0.001),
            ("seconds", 1),
            ("minutes", 60),
            ("hours", 60 * 60),
            ("days", 60 * 60 * 24),
            ("weeks", 60 * 60 * 24 * 7),
        ],
    )
    def test_smoke(self, mocker: MockerFixture, unit: str, factor: float) -> None:
        mock_reply = mocker.MagicMock()
        content_property = mocker.PropertyMock()
        type(mock_reply).content = content_property
        content_property.return_value = '<a value="42"></a>'
        mocker.patch("requests.Session.get", return_value=mock_reply)

        url = "nourl"
        now = datetime.now(timezone.utc)
        result = XPathDeltaWakeup(
            "foo", xpath="/a/@value", url=url, timeout=5, unit=unit
        ).check(now)
        assert result == now + timedelta(seconds=42) * factor

    def test_create(self) -> None:
        check = XPathDeltaWakeup.create(
            "name",
            config_section(
                {
                    "xpath": "/valid",
                    "url": "nourl",
                    "timeout": "20",
                    "unit": "weeks",
                }
            ),
        )
        assert check._unit == "weeks"

    def test_create_wrong_unit(self) -> None:
        with pytest.raises(ConfigurationError):
            XPathDeltaWakeup.create(
                "name",
                config_section(
                    {
                        "xpath": "/valid",
                        "url": "nourl",
                        "timeout": "20",
                        "unit": "unknown",
                    }
                ),
            )

    def test_init_wrong_unit(self) -> None:
        with pytest.raises(ValueError, match=r".*unit.*"):
            XPathDeltaWakeup(
                "name", url="url", xpath="/a", timeout=5, unit="unknownunit"
            )
