import os
import pytest
from app import create_app
from app.config import TestConfig


@pytest.fixture
def app_instance(tmp_path):
    db_file = os.path.join(tmp_path, "test_sms.db")

    class LocalTestConfig(TestConfig):
        DATABASE_PATH = db_file

    application = create_app(config_class=LocalTestConfig, init_db=True)
    yield application


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


@pytest.fixture
def db(app_instance):
    return app_instance.extensions["db"]
