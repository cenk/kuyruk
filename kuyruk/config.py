import os
import ast
import sys
import types
import logging
import importer
import multiprocessing

logger = logging.getLogger(__name__)


class Config(object):
    """Kuyruk configuration object. Default values are defined as
    class attributes.

    """
    # Connection Options
    ####################

    RABBIT_HOST = 'localhost'
    """RabbitMQ host."""

    RABBIT_PORT = 5672
    """RabbitMQ port."""

    RABBIT_VIRTUAL_HOST = '/'
    """RabbitMQ virtual host."""

    RABBIT_USER = 'guest'
    """RabbitMQ user."""

    RABBIT_PASSWORD = 'guest'
    """RabbitMQ password."""

    # Worker Options
    ################

    WORKER_CLASS = 'kuyruk.worker.Worker'
    """Worker implementation class. It can be replaced with a subclass of
    :class:`~kuyruk.worker.Worker` to change specific behavior."""

    IMPORT_PATH = None
    """Worker imports tasks from this directory."""

    IMPORTS = []
    """By default worker imports the task modules lazily when it receive a
    task from the queue. If you specify the modules here they will be
    imported when the worker is started."""

    EAGER = False
    """Run tasks in the process without sending to queue. Useful in tests."""

    MAX_LOAD = None
    """Stop consuming queue when the load goes above this level."""

    MAX_WORKER_RUN_TIME = None
    """Gracefully shutdown worker after running this seconds.
    Master will detect that the worker is exited and will spawn a new
    worker with identical config.
    Can be used to force loading of new application code."""

    MAX_TASK_RUN_TIME = None
    """Fail the task if it takes more than this seconds."""

    LOGGING_LEVEL = 'INFO'
    """Logging level of root logger."""

    LOGGING_CONFIG = None
    """INI style logging configuration file.
    This has pecedence over ``LOGGING_LEVEL``."""

    SENTRY_DSN = None
    """Send exceptions to Sentry. Raven must be installed in order that
    this feature to work."""

    def from_object(self, obj):
        """Load values from an object."""
        for key in dir(obj):
            if key.isupper():
                value = getattr(obj, key)
                setattr(self, key, value)
        logger.info("Config is loaded from object: %r", obj)

    def from_dict(self, d):
        """Load values from a dict."""
        for key, value in d.iteritems():
            if key.isupper():
                setattr(self, key, value)
        logger.info("Config is loaded from dict: %r", d)

    def from_pymodule(self, module_name):
        def readfile(conn):
            logger.debug("Reading config file from seperate process...")
            try:
                mdl = importer.import_module(module_name)
                values = {}
                for key, value in mdl.__dict__.iteritems():
                    if (key.isupper() and not isinstance(value, types.ModuleType)):
                        values[key] = value
                self.from_dict(values)
                logger.info("Config is loaded from module: %s", module_name)
                conn.send(values)
                logger.debug("Config read successfully")
            except:
                logger.exception("Cannot read config")
                conn.send(None)
                raise

        parent_conn, child_conn = multiprocessing.Pipe()
        process = multiprocessing.Process(target=readfile,
                                          args=(child_conn, ))
        process.start()
        values = parent_conn.recv()
        process.join()
        if values is None:
            print "Cannot load config module: %s" % module_name
            sys.exit(1)

        self.from_dict(values)
        logger.info("Config is loaded from module: %s", module_name)

    def from_pyfile(self, filename):
        """Load values from a Python file."""
        # Read the config file from a seperate process because it may contain
        # import statements doing import from user code. No user code should
        # be imported to master because they have to be imported in workers
        # after the master has forked. Otherwise newly created workers
        # cannot load new code after the master has started.
        def readfile(conn):
            logger.debug("Reading config file from seperate process...")
            try:
                globals_, locals_ = {}, {}
                execfile(filename, globals_, locals_)
                values = {}
                for key, value in locals_.iteritems():
                    if (key.isupper() and
                            not isinstance(value, types.ModuleType)):
                        values[key] = value
                conn.send(values)
                logger.debug("Config read successfully")
            except:
                logger.exception("Cannot read config")
                conn.send(None)
                raise

        parent_conn, child_conn = multiprocessing.Pipe()
        process = multiprocessing.Process(target=readfile,
                                          args=(child_conn, ))
        process.start()
        values = parent_conn.recv()
        process.join()
        if values is None:
            print "Cannot load config file: %s" % filename
            sys.exit(1)

        self.from_dict(values)
        logger.info("Config is loaded from file: %s", filename)

    def from_env_vars(self):
        """Load values from environment variables."""
        for key, value in os.environ.iteritems():
            if key.startswith('KUYRUK_'):
                key = key.lstrip('KUYRUK_')
                self._eval_item(key, value)

    def from_cmd_args(self, args):
        """Load values from command line arguments."""
        def to_attr(option):
            return option.upper().replace('-', '_')

        for key, value in vars(args).iteritems():
            if value is not None:
                key = to_attr(key)
                self._eval_item(key, value)

    def _eval_item(self, key, value):
        if hasattr(Config, key):
            try:
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                pass
            setattr(self, key, value)
