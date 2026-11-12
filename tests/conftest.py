def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: needs the running stack with GPU engines/workers")
    config.addinivalue_line("markers", "db: needs Postgres")
