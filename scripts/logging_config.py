import logging
import os
import sys


class AllowBelowSeverity(logging.Filter):

    """
    Allows only records less severe than a given level (the opposite of what
    the normal logging level filtering does.
    """

    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno < self.level


class LoggingConfig(object):
    global_level = logging.DEBUG
    stdout_level = logging.INFO
    stderr_level = logging.ERROR

    file_formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-5.5s|%(module)10.10s:%(lineno)4.4d| "
        "%(message)s",
        datefmt="%m/%d %H:%M:%S",
    )

    console_formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-5.5s| %(message)s", datefmt="%H:%M:%S"
    )

    def __init__(self, use_console=True, set_fmt=True):
        self.logger = logging.getLogger()
        self.global_level = logging.DEBUG
        self.use_console = use_console
        self.set_fmt = set_fmt

    def add_stream_handler(self, stream, level=logging.DEBUG):
        handler = logging.StreamHandler(stream)
        handler.setLevel(level)
        if self.set_fmt:
            handler.setFormatter(self.console_formatter)
        self.logger.addHandler(handler)
        return handler

    def add_console_handlers(self):
        stdout_handler = self.add_stream_handler(sys.stdout, level=self.stdout_level)
        # only pass records *below* STDERR_LEVEL to stdout, to avoid
        # duplication
        stdout_handler.addFilter(AllowBelowSeverity(self.stderr_level))

        self.add_stream_handler(sys.stderr, self.stderr_level)

    def add_file_handler(self, file_path, level=logging.DEBUG, log_dir=None):
        if log_dir:
            file_path = os.path.join(log_dir, file_path)
        handler = logging.FileHandler(file_path)
        handler.setLevel(level)
        if self.set_fmt:
            handler.setFormatter(self.file_formatter)
        self.logger.addHandler(handler)
        return handler

    def _add_file_handlers_for_all_levels(self, log_dir, log_name):
        for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
            file_name = "%s.%s" % (log_name, logging.getLevelName(level))
            self.add_file_handler(file_name, level=level, log_dir=log_dir)

    def add_debug_file_handlers(self, log_dir, log_name=None):
        raise NotImplementedError

    def _clear_all_handlers(self):
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            # Attempt to close the handler. If it's already closed a KeyError
            # will be generated. http://bugs.python.org/issue8581
            try:
                handler.close()
            except KeyError:
                pass

    def configure_logging(self, use_console=True, verbose=False):
        self._clear_all_handlers()  # see comment at top of file
        self.logger.setLevel(self.global_level)

        if verbose:
            self.stdout_level = logging.DEBUG
        if use_console:
            self.add_console_handlers()
