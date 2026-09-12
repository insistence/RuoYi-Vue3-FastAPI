import os


class Config:
    frontend_url = os.environ.get('TEST_FRONTEND_URL', 'http://localhost:80')
    backend_url = os.environ.get('TEST_BACKEND_URL', 'http://localhost:9099')
    browser_channel = os.environ.get('TEST_BROWSER_CHANNEL') or None
    swagger_disabled = os.environ.get('TEST_SWAGGER_DISABLED', 'true').lower() == 'true'
