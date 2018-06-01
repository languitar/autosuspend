import http.server
import os
import threading

import pytest


@pytest.fixture
def stub_server(request):
    previous_cwd = os.getcwd()
    if request and hasattr(request, 'param'):
        os.chdir(request.param)

    server = http.server.HTTPServer(('localhost', 0),
                                    http.server.SimpleHTTPRequestHandler)
    threading.Thread(target=server.serve_forever).start()

    yield server

    server.shutdown()
    if request and hasattr(request, 'param'):
        os.chdir(previous_cwd)
