import base64
import http.server
import os
import threading

import pytest


class AuthHandler(http.server.SimpleHTTPRequestHandler):
    def do_HEAD(self):  # noqa: required name
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_AUTHHEAD(self):  # noqa: required name
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm=\"Test\"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):  # noqa: required name
        key = '{}:{}'.format('user', 'pass').encode('ascii')
        key = base64.b64encode(key)
        valid_header = b'Basic ' + key

        auth_header = self.headers.get(
            'Authorization', '').encode('ascii')

        if self.headers['Authorization'] is None:
            self.do_AUTHHEAD()
            self.wfile.write(b'no auth header received')
        elif auth_header == valid_header:
            http.server.SimpleHTTPRequestHandler.do_GET(self)
        else:
            self.do_AUTHHEAD()
            self.wfile.write(auth_header)
            self.wfile.write(b'not authenticated')


def _serve(request, handler):
    previous_cwd = os.getcwd()

    target_dir = os.path.join(os.path.dirname(__file__), 'test_data')
    if request and hasattr(request, 'param'):
        target_dir = request.param
    os.chdir(target_dir)

    server = http.server.HTTPServer(('localhost', 0), handler)

    def resource_address(resource: str) -> str:
        return 'http://localhost:{}/{}'.format(
            server.server_address[1], resource)

    server.resource_address = resource_address

    threading.Thread(target=server.serve_forever).start()

    yield server

    server.shutdown()
    os.chdir(previous_cwd)


@pytest.fixture
def stub_server(request):
    yield from _serve(request, http.server.SimpleHTTPRequestHandler)


@pytest.fixture
def stub_auth_server(request):
    yield from _serve(request, AuthHandler)
