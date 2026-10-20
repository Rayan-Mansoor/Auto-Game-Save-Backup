import logging

from saveix.core.config import Config
from saveix.core.logs import setup_logging


def test_logs_go_to_rotating_file():
    config = Config()
    path = setup_logging(config)
    setup_logging(config)  # setting up twice does not duplicate lines
    logging.getLogger("saveix").info("hello from the test")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert path.read_text(encoding="utf-8").count("hello from the test") == 1
    for handler in list(logging.getLogger().handlers):
        if getattr(handler, "_saveix", False):
            logging.getLogger().removeHandler(handler)
            handler.close()
