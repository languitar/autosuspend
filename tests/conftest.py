import http.server
import os
import threading

import pytest


@pytest.fixture
def stub_server(request):
    previous_cwd = os.getcwd()

    target_dir = os.path.join(os.path.dirname(__file__), 'test_data')
    if request and hasattr(request, 'param'):
        target_dir = request.param
    os.chdir(target_dir)

    server = http.server.HTTPServer(('localhost', 0),
                                    http.server.SimpleHTTPRequestHandler)

    def resource_address(resource: str) -> str:
        return 'http://localhost:{}/{}'.format(
            server.server_address[1], resource)

    server.resource_address = resource_address

    threading.Thread(target=server.serve_forever).start()

    yield server

    server.shutdown()
    os.chdir(previous_cwd)
