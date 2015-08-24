# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2015
# Author: Lucas Meneghel Rodrigues <lmr@redhat.com>

"""
Avocado VT plugin
"""

import os
import sys
import logging
import Queue
import time
import imp

from avocado.core import result
from avocado.core import loader
from avocado.core import output
from avocado.core import exceptions
from avocado.core import multiplexer
from avocado.core import test
from avocado.core.settings import settings
from avocado.core.plugins import plugin
from avocado.utils import stacktrace
from avocado.utils import genio

# avocado-vt no longer needs autotest for the majority of its functionality,
# except by:
# 1) Run autotest on VMs
# 2) Multi host migration
# 3) Proper avocado-vt test status handling
# As in those cases we might want to use autotest, let's have a way for
# users to specify their autotest from a git clone location.
AUTOTEST_PATH = None

if 'AUTOTEST_PATH' in os.environ:
    AUTOTEST_PATH = os.path.expanduser(os.environ['AUTOTEST_PATH'])
    client_dir = os.path.join(os.path.abspath(AUTOTEST_PATH), 'client')
    setup_modules_path = os.path.join(client_dir, 'setup_modules.py')
    setup_modules = imp.load_source('autotest_setup_modules',
                                    setup_modules_path)
    setup_modules.setup(base_path=client_dir,
                        root_module_name="autotest.client")

from autotest.client.shared import error

from virttest import asset
from virttest import bootstrap
from virttest import cartesian_config
from virttest import data_dir
from virttest import defaults
from virttest import env_process
from virttest import funcatexit
from virttest import standalone_test
from virttest import utils_env
from virttest import utils_misc
from virttest import utils_params
from virttest import version
from virttest import storage

from virttest.standalone_test import SUPPORTED_TEST_TYPES
from virttest.standalone_test import SUPPORTED_LIBVIRT_URIS
from virttest.standalone_test import SUPPORTED_LIBVIRT_DRIVERS
from virttest.standalone_test import SUPPORTED_IMAGE_TYPES
from virttest.standalone_test import SUPPORTED_DISK_BUSES
from virttest.standalone_test import SUPPORTED_NIC_MODELS
from virttest.standalone_test import SUPPORTED_NET_TYPES


_PROVIDERS_DOWNLOAD_DIR = os.path.join(data_dir.get_test_providers_dir(),
                                       'downloads')

if len(os.listdir(_PROVIDERS_DOWNLOAD_DIR)) == 0:
    raise EnvironmentError("Bootstrap missing. "
                           "Execute 'avocado vt-bootstrap' or disable this "
                           "plugin to get rid of this message")


class VirtTestResult(result.HumanTestResult):

    """
    Virt Test compatibility layer Result class.
    """

    def __init__(self, stream, args):
        """
        Creates an instance of RemoteTestResult.

        :param stream: an instance of :class:`avocado.core.output.View`.
        :param args: an instance of :class:`argparse.Namespace`.
        """
        result.HumanTestResult.__init__(self, stream, args)
        self.output = '-'
        self.setup()

    def setup(self):
        """
        Run the setup needed before tests start to run (restore test images).
        """
        options = self.args
        if options.vt_config:
            parent_config_dir = os.path.dirname(
                os.path.dirname(options.vt_config))
            parent_config_dir = os.path.dirname(parent_config_dir)
            options.vt_type = parent_config_dir

        kwargs = {'options': options}

        failed = False

        bg = utils_misc.InterruptedThread(bootstrap.setup, kwargs=kwargs)
        t_begin = time.time()
        bg.start()

        self.stream.notify(event='message', msg="SETUP      :  ",
                           skip_newline=True)
        while bg.isAlive():
            self.stream.notify_progress(True)
            time.sleep(0.1)

        reason = None
        try:
            bg.join()
        except Exception, e:
            failed = True
            reason = e

        t_end = time.time()
        t_elapsed = t_end - t_begin
        state = dict()
        state['time_elapsed'] = t_elapsed
        if not failed:
            self.stream.set_test_status(status='PASS', state=state)
        else:
            self.stream.set_test_status(status='FAIL', state=state)
            self.stream.notify(event='error', msg="Setup error: %s" % reason)
            sys.exit(-1)

        return True


def configure_console_logging(loglevel=logging.DEBUG):
    """
    Simple helper for adding a file logger to the root logger.
    """
    logger = logging.getLogger()
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(loglevel)

    fmt = ('%(asctime)s %(module)-10.10s L%(lineno)-.4d %('
           'levelname)-5.5s| %(message)s')
    formatter = logging.Formatter(fmt=fmt, datefmt='%H:%M:%S')

    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return stream_handler


def configure_file_logging(logfile, loglevel=logging.DEBUG):
    """
    Add a file logger to the root logger.

    This file logger contains the formatting of the avocado
    job log. This way all things logged by autotest go
    straight to the avocado job log.
    """
    logger = logging.getLogger()
    file_handler = logging.FileHandler(filename=logfile)
    file_handler.setLevel(loglevel)
    fmt = ('%(asctime)s %(module)-10.10s L%(lineno)-.4d %('
           'levelname)-5.5s| %(message)s')
    formatter = logging.Formatter(fmt=fmt, datefmt='%H:%M:%S')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return file_handler


def guest_listing(options, view):
    term_support = output.TermSupport()
    if options.vt_type == 'lvsb':
        raise ValueError("No guest types available for lvsb testing")
    index = 0
    view.notify(event='minor', msg=("Searched %s for guest images\n" %
                                    os.path.join(data_dir.get_data_dir(),
                                                 'images')))
    view.notify(event='minor', msg="Available guests in config:")
    view.notify(msg='')
    guest_name_parser = standalone_test.get_guest_name_parser(options)
    guest_name_parser.only_filter('i440fx')
    for params in guest_name_parser.get_dicts():
        index += 1
        base_dir = params.get("images_base_dir", data_dir.get_data_dir())
        image_name = storage.get_image_filename(params, base_dir)
        name = params['name']
        if os.path.isfile(image_name):
            out = name
        else:
            out = (name + " " +
                   term_support.warn_header_str("(missing %s)" %
                                                os.path.basename(image_name)))
        view.notify(event='minor', msg=out)


class VirtTestLoader(loader.TestLoader):

    name = 'vt'

    def __init__(self, args):
        super(VirtTestLoader, self).__init__(args)
        self._fill_optional_args()

    def _fill_optional_args(self):
        def add_if_not_exist(arg, value):
            if not hasattr(self.args, arg):
                setattr(self.args, arg, value)
        add_if_not_exist('vt_config', None)
        add_if_not_exist('vt_verbose', True)
        add_if_not_exist('vt_log_level', 'debug')
        add_if_not_exist('vt_console_level', 'debug')
        add_if_not_exist('vt_datadir', data_dir.get_data_dir())
        add_if_not_exist('vt_config', None)
        add_if_not_exist('vt_arch', None)
        add_if_not_exist('vt_machine_type', None)
        add_if_not_exist('vt_keep_guest_running', False)
        add_if_not_exist('vt_keep_image_between_tests', False)
        add_if_not_exist('vt_mem', 1024)
        add_if_not_exist('vt_no_filter', '')
        add_if_not_exist('vt_qemu_bin', None)
        add_if_not_exist('vt_dst_qemu_bin', None)
        add_if_not_exist('vt_nettype', 'user')
        add_if_not_exist('vt_only_type_specific', False)
        add_if_not_exist('vt_tests', '')
        add_if_not_exist('vt_connect_uri', 'qemu:///system')
        add_if_not_exist('vt_accel', 'kvm')
        add_if_not_exist('vt_monitor', 'human')
        add_if_not_exist('vt_smp', 1)
        add_if_not_exist('vt_image_type', 'qcow2')
        add_if_not_exist('vt_nic_model', 'virtio_net')
        add_if_not_exist('vt_disk_bus', 'virtio_blk')
        add_if_not_exist('vt_vhost', 'off')
        add_if_not_exist('vt_malloc_perturb', 'yes')
        add_if_not_exist('vt_qemu_sandbox', 'on')
        add_if_not_exist('vt_tests', '')
        add_if_not_exist('show_job_log', False)
        add_if_not_exist('test_lister', True)

    def _get_parser(self):
        options_processor = VirtTestOptionsProcess(self.args)
        return options_processor.get_parser()

    def get_extra_listing(self):
        if self.args.vt_list_guests:
            use_paginator = self.args.paginator == 'on'
            view = output.View(use_paginator=use_paginator)
            try:
                guest_listing(self.args, view)
            finally:
                view.cleanup()
            sys.exit(0)

    @staticmethod
    def get_type_label_mapping():
        """
        Get label mapping for display in test listing.

        :return: Dict {TestClass: 'TEST_LABEL_STRING'}
        """
        return {VirtTest: 'VT'}

    @staticmethod
    def get_decorator_mapping():
        """
        Get label mapping for display in test listing.

        :return: Dict {TestClass: decorator function}
        """
        term_support = output.TermSupport()
        return {VirtTest: term_support.healthy_str}

    def discover(self, url, list_tests=False):
        try:
            cartesian_parser = self._get_parser()
        except Exception, details:
            raise EnvironmentError(details)
        if url is not None:
            try:
                cartesian_parser.only_filter(url)
            # If we have a LexerError, this means
            # the url passed is invalid in the cartesian
            # config parser, hence it should be ignored.
            # just return an empty params list and let
            # the other test plugins to handle the URL.
            except cartesian_config.LexerError:
                return []
        elif list_tests is loader.DEFAULT and not self.args.vt_config:
            # By default don't run anythinig unless vt_config provided
            return []
        # Create test_suite
        test_suite = []
        for params in (_ for _ in cartesian_parser.get_dicts()):
            # We want avocado to inject params coming from its multiplexer into
            # the test params. This will allow users to access avocado params
            # from inside virt tests. This feature would only work if the virt
            # test in question is executed from inside avocado.
            params['avocado_inject_params'] = True
            test_name = params.get("_short_name_map_file")["subtests.cfg"]
            params['id'] = test_name
            test_parameters = {'name': test_name,
                               'params': params}
	    if self.args.verbose:
		print("Discover: %s" % test_name)
            test_suite.append((VirtTest, test_parameters))
        return test_suite


class VirtTest(test.Test):

    """
    Mininal test class used to run a virt test.
    """

    env_version = utils_env.get_env_version()

    def __init__(self, methodName='runTest', name=None, params=None,
                 base_logdir=None, tag=None, job=None, runner_queue=None):
        del name
        options = job.args
        self.bindir = data_dir.get_root_dir()
        self.virtdir = os.path.join(self.bindir, 'shared')

        self.iteration = 0
        if options.vt_config:
            name = params.get("shortname")
        else:
            name = params.get("_short_name_map_file")["subtests.cfg"]
        self.outputdir = None
        self.resultsdir = None
        self.logfile = None
        self.file_handler = None
        self.background_errors = Queue.Queue()
        self.whiteboard = None
        super(VirtTest, self).__init__(methodName=methodName, name=name,
                                       params=params, base_logdir=base_logdir,
                                       tag=tag, job=job,
                                       runner_queue=runner_queue)
        self.builddir = os.path.join(self.workdir, 'backends',
                                     params.get("vm_type"))
        self.tmpdir = os.path.dirname(self.workdir)

        self.params = utils_params.Params(params)
        # Here we turn the data the multiplexer injected into the params and
        # turn it into an AvocadoParams object, that will allow users to
        # access data from it. Example:
        # sleep_length = test.avocado_params.get('sleep_length', default=1)
        p = params.get('avocado_params', None)
        if p is not None:
            params, mux_path = p[0], p[1]
        else:
            params, mux_path = [], []
        self.avocado_params = multiplexer.AvocadoParams(params, self.name,
                                                        self.tag,
                                                        mux_path,
                                                        self.default_params)

        self.debugdir = self.logdir
        utils_misc.set_log_file_dir(self.logdir)

    def _start_logging(self):
        super(VirtTest, self)._start_logging()
        root_logger = logging.getLogger()
        root_logger.addHandler(self.file_handler)

    def _stop_logging(self):
        super(VirtTest, self)._stop_logging()
        root_logger = logging.getLogger()
        root_logger.removeHandler(self.file_handler)

    def write_test_keyval(self, d):
        self.whiteboard = str(d)

    def verify_background_errors(self):
        """
        Verify if there are any errors that happened on background threads.

        :raise Exception: Any exception stored on the background_errors queue.
        """
        try:
            exc = self.background_errors.get(block=False)
        except Queue.Empty:
            pass
        else:
            raise exc[1], None, exc[2]

    def runTest(self):
        try:
            self._runTest()
        # This trick will give better reporting of virt tests
        # being executed into avocado (skips and errors will display correctly)
        except error.TestNAError, details:
            raise exceptions.TestNAError(details)
        except error.TestError, details:
            raise exceptions.TestError(details)
        except error.TestFail, details:
            raise exceptions.TestFail(details)

    def _runTest(self):
        params = self.params

        # If a dependency test prior to this test has failed, let's fail
        # it right away as TestNA.
        if params.get("dependency_failed") == 'yes':
            raise error.TestNAError("Test dependency failed")

        # Report virt test version
        logging.info(version.get_pretty_version_info())
        # Report the parameters we've received and write them as keyvals
        logging.info("Starting test %s", self.tag)
        logging.debug("Test parameters:")
        keys = params.keys()
        keys.sort()
        for key in keys:
            logging.debug("    %s = %s", key, params[key])

        # Warn of this special condition in related location in output & logs
        if os.getuid() == 0 and params.get('nettype', 'user') == 'user':
            logging.warning("")
            logging.warning("Testing with nettype='user' while running "
                            "as root may produce unexpected results!!!")
            logging.warning("")

        # Open the environment file
        env_filename = os.path.join(
            data_dir.get_backend_dir(params.get("vm_type")),
            params.get("env", "env"))
        env = utils_env.Env(env_filename, self.env_version)

        test_passed = False
        t_type = None

        try:
            try:
                try:
                    subtest_dirs = []
                    test_filter = bootstrap.test_filter

                    other_subtests_dirs = params.get("other_tests_dirs", "")
                    for d in other_subtests_dirs.split():
                        d = os.path.join(*d.split("/"))
                        subtestdir = os.path.join(self.bindir, d, "tests")
                        if not os.path.isdir(subtestdir):
                            raise error.TestError("Directory %s does not "
                                                  "exist" % subtestdir)
                        subtest_dirs += data_dir.SubdirList(subtestdir,
                                                            test_filter)

                    provider = params.get("provider", None)

                    if provider is None:
                        # Verify if we have the correspondent source file for
                        # it
                        generic_subdirs = asset.get_test_provider_subdirs(
                            'generic')
                        for generic_subdir in generic_subdirs:
                            subtest_dirs += data_dir.SubdirList(generic_subdir,
                                                                test_filter)
                        specific_subdirs = asset.get_test_provider_subdirs(
                            params.get("vm_type"))
                        for specific_subdir in specific_subdirs:
                            subtest_dirs += data_dir.SubdirList(
                                specific_subdir, bootstrap.test_filter)
                    else:
                        provider_info = asset.get_test_provider_info(provider)
                        for key in provider_info['backends']:
                            subtest_dirs += data_dir.SubdirList(
                                provider_info['backends'][key]['path'],
                                bootstrap.test_filter)

                    subtest_dir = None

                    # Get the test routine corresponding to the specified
                    # test type
                    logging.debug("Searching for test modules that match "
                                  "'type = %s' and 'provider = %s' "
                                  "on this cartesian dict",
                                  params.get("type"),
                                  params.get("provider", None))

                    t_types = params.get("type").split()
                    # Make sure we can load provider_lib in tests
                    for s in subtest_dirs:
                        if os.path.dirname(s) not in sys.path:
                            sys.path.insert(0, os.path.dirname(s))

                    test_modules = {}
                    for t_type in t_types:
                        for d in subtest_dirs:
                            module_path = os.path.join(d, "%s.py" % t_type)
                            if os.path.isfile(module_path):
                                logging.debug("Found subtest module %s",
                                              module_path)
                                subtest_dir = d
                                break
                        if subtest_dir is None:
                            msg = ("Could not find test file %s.py on test"
                                   "dirs %s" % (t_type, subtest_dirs))
                            raise error.TestError(msg)
                        # Load the test module
                        f, p, d = imp.find_module(t_type, [subtest_dir])
                        test_modules[t_type] = imp.load_module(t_type, f, p, d)
                        f.close()

                    # Preprocess
                    try:
                        params = env_process.preprocess(self, params, env)
                    finally:
                        env.save()

                    # Run the test function
                    for t_type in t_types:
                        test_module = test_modules[t_type]
                        run_func = utils_misc.get_test_entrypoint_func(
                            t_type, test_module)
                        try:
                            run_func(self, params, env)
                            self.verify_background_errors()
                        finally:
                            env.save()
                    test_passed = True
                    error_message = funcatexit.run_exitfuncs(env, t_type)
                    if error_message:
                        raise error.TestWarn("funcatexit failed with: %s" %
                                             error_message)

                except Exception:
                    if t_type is not None:
                        error_message = funcatexit.run_exitfuncs(env, t_type)
                        if error_message:
                            logging.error(error_message)
                    try:
                        env_process.postprocess_on_error(self, params, env)
                    finally:
                        env.save()
                    raise

            finally:
                # Postprocess
                try:
                    try:
                        env_process.postprocess(self, params, env)
                    except Exception, e:
                        if test_passed:
                            raise
                        logging.error("Exception raised during "
                                      "postprocessing: %s", e)
                finally:
                    env.save()

        except Exception, e:
            if params.get("abort_on_error") != "yes":
                raise
            # Abort on error
            logging.info("Aborting job (%s)", e)
            if params.get("vm_type") == "qemu":
                for vm in env.get_all_vms():
                    if vm.is_dead():
                        continue
                    logging.info("VM '%s' is alive.", vm.name)
                    for m in vm.monitors:
                        logging.info("It has a %s monitor unix socket at: %s",
                                     m.protocol, m.filename)
                    logging.info("The command line used to start it was:\n%s",
                                 vm.make_qemu_command())
                raise error.JobError("Abort requested (%s)" % e)

        return test_passed

    def _run_avocado(self):
        """
        Auxiliary method to run_avocado.

        We have to override this method because the avocado-vt plugin
        has to override the behavior that tests shouldn't raise
        exceptions.TestNAError by themselves in avocado. In the old
        avocado-vt case, that rule is not in place, so we have to be
        a little more lenient for correct test status reporting.
        """
        testMethod = getattr(self, self._testMethodName)
        self._start_logging()
        self.sysinfo_logger.start_test_hook()
        test_exception = None
        cleanup_exception = None
        stdout_check_exception = None
        stderr_check_exception = None
        try:
            self.setUp()
        except exceptions.TestNAError, details:
            stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
            raise exceptions.TestNAError(details)
        except Exception, details:
            stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
            raise exceptions.TestSetupFail(details)
        try:
            testMethod()
        except Exception, details:
            stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
            test_exception = details
        finally:
            try:
                self.tearDown()
            except Exception, details:
                stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
                cleanup_exception = details

        whiteboard_file = os.path.join(self.logdir, 'whiteboard')
        genio.write_file(whiteboard_file, self.whiteboard)

        if self.job is not None:
            job_standalone = getattr(self.job.args, 'standalone', False)
            output_check_record = getattr(self.job.args,
                                          'output_check_record', 'none')
            no_record_mode = (not job_standalone and
                              output_check_record == 'none')
            disable_output_check = (not job_standalone and
                                    getattr(self.job.args,
                                            'output_check', 'on') == 'off')

            if job_standalone or no_record_mode:
                if not disable_output_check:
                    try:
                        self.check_reference_stdout()
                    except Exception, details:
                        stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
                        stdout_check_exception = details
                    try:
                        self.check_reference_stderr()
                    except Exception, details:
                        stacktrace.log_exc_info(sys.exc_info(), logger='avocado.test')
                        stderr_check_exception = details
            elif not job_standalone:
                if output_check_record in ['all', 'stdout']:
                    self.record_reference_stdout()
                if output_check_record in ['all', 'stderr']:
                    self.record_reference_stderr()

        # pylint: disable=E0702
        if test_exception is not None:
            raise test_exception
        elif cleanup_exception is not None:
            raise exceptions.TestSetupFail(cleanup_exception)
        elif stdout_check_exception is not None:
            raise stdout_check_exception
        elif stderr_check_exception is not None:
            raise stderr_check_exception

        self.status = 'PASS'
        self.sysinfo_logger.end_test_hook()


class VirtTestOptionsProcess(object):

    """
    Pick virt test options and parse them to get to a cartesian parser.
    """

    def __init__(self, options):
        """
        Parses options and initializes attributes.
        """
        self.options = options
        # There are a few options from the original virt-test runner
        # that don't quite make sense for avocado (avocado implements a
        # better version of the virt-test feature).
        # So let's just inject some values into options.
        self.options.vt_verbose = False
        self.options.vt_log_level = logging.DEBUG
        self.options.vt_console_level = logging.DEBUG
        self.options.vt_no_downloads = False
        self.options.vt_selinux_setup = False

        # Here we'll inject values from the config file.
        # Doing this makes things configurable yet the number of options
        # is not overwhelming.
        # setup section
        self.options.vt_keep_image = settings.get_value(
            'vt.setup', 'keep_image', key_type=bool)
        self.options.vt_keep_image_between_tests = settings.get_value(
            'vt.setup', 'keep_image_between_tests', key_type=bool)
        self.options.vt_keep_guest_running = settings.get_value(
            'vt.setup', 'keep_guest_running', key_type=bool)
        # common section
        self.options.vt_data_dir = settings.get_value(
            'vt.common', 'data_dir', default=None)
        self.options.vt_type_specific = settings.get_value(
            'vt.common', 'type_specific_only', key_type=bool)
        self.options.vt_mem = settings.get_value(
            'vt.common', 'mem', key_type=int)
        self.options.vt_nettype = settings.get_value(
            'vt.common', 'nettype', default=None)
        self.options.vt_netdst = settings.get_value(
            'vt.common', 'netdst', default='virbr0')
        # qemu section
        self.options.vt_accel = settings.get_value(
            'vt.qemu', 'accel', default='kvm')
        self.options.vt_vhost = settings.get_value(
            'vt.qemu', 'vhost', default='off')
        self.options.vt_monitor = settings.get_value(
            'vt.qemu', 'monitor', default='human')
        self.options.vt_smp = settings.get_value(
            'vt.qemu', 'smp', default='2')
        self.options.vt_image_type = settings.get_value(
            'vt.qemu', 'image_type', default='qcow2')
        self.options.vt_nic_model = settings.get_value(
            'vt.qemu', 'nic_model', default='virtio_net')
        self.options.vt_disk_bus = settings.get_value(
            'vt.qemu', 'disk_bus', default='virtio_blk')
        self.options.vt_qemu_sandbox = settings.get_value(
            'vt.qemu', 'sandbox', default='on')
        self.options.vt_qemu_defconfig = settings.get_value(
            'vt.qemu', 'defconfig', default='yes')
        self.options.vt_malloc_perturb = settings.get_value(
            'vt.qemu', 'malloc_perturb', default='yes')

        # debug section
        self.options.vt_no_cleanup = settings.get_value(
            'vt.debug', 'no_cleanup', key_type=bool, default=False)

        self.cartesian_parser = None

    def _process_qemu_bin(self):
        """
        Puts the value of the qemu bin option in the cartesian parser command.
        """
        qemu_bin_setting = ('option --vt-qemu-bin or '
                            'config vt.qemu.qemu_bin')
        if self.options.vt_config and self.options.vt_qemu_bin is None:
            logging.info("Config provided and no %s set. Not trying "
                         "to automatically set qemu bin.", qemu_bin_setting)
        else:
            (qemu_bin_path, qemu_img_path, qemu_io_path,
             qemu_dst_bin_path) = standalone_test.find_default_qemu_paths(
                self.options.vt_qemu_bin, self.options.vt_dst_qemu_bin)
            self.cartesian_parser.assign("qemu_binary", qemu_bin_path)
            self.cartesian_parser.assign("qemu_img_binary", qemu_img_path)
            self.cartesian_parser.assign("qemu_io_binary", qemu_io_path)
            if qemu_dst_bin_path is not None:
                self.cartesian_parser.assign("qemu_dst_binary",
                                             qemu_dst_bin_path)

    def _process_qemu_img(self):
        """
        Puts the value of the qemu bin option in the cartesian parser command.
        """
        qemu_img_setting = ('option --vt-qemu-img or '
                            'config vt.qemu.qemu_img')
        if self.options.vt_config and self.options.vt_qemu_bin is None:
            logging.info("Config provided and no %s set. Not trying "
                         "to automatically set qemu bin", qemu_img_setting)
        else:
            (_, qemu_img_path,
             _, _) = standalone_test.find_default_qemu_paths(
                self.options.vt_qemu_bin, self.options.vt_dst_qemu_bin)
            self.cartesian_parser.assign("qemu_img_binary", qemu_img_path)

    def _process_qemu_accel(self):
        """
        Puts the value of the qemu bin option in the cartesian parser command.
        """
        if self.options.vt_accel == 'tcg':
            self.cartesian_parser.assign("disable_kvm", "yes")

    def _process_bridge_mode(self):
        nettype_setting = 'config vt.qemu.nettype'
        if not self.options.vt_config:
            # Let's select reasonable defaults depending on vt_type
            if self.options.vt_type == 'qemu':
                self.options.vt_nettype = (self.options.vt_nettype if
                                           self.options.vt_nettype else 'user')
            else:
                self.options.vt_nettype = (self.options.vt_nettype if
                                           self.options.vt_nettype else 'bridge')

            if self.options.vt_nettype not in SUPPORTED_NET_TYPES:
                raise ValueError("Invalid %s '%s'. "
                                 "Valid values: (%s)" %
                                 (nettype_setting,
                                  self.options.vt_nettype,
                                  ", ".join(SUPPORTED_NET_TYPES)))
            if self.options.vt_nettype == 'bridge':
                if os.getuid() != 0:
                    raise ValueError("In order to use %s '%s' you "
                                     "need to be root" % (nettype_setting,
                                                          self.options.vt_nettype))
                self.cartesian_parser.assign("nettype", "bridge")
                self.cartesian_parser.assign("netdst", self.options.vt_netdst)
            elif self.options.vt_nettype == 'user':
                self.cartesian_parser.assign("nettype", "user")
            elif self.options.vt_nettype == 'none':
                self.cartesian_parser.assign("nettype", "none")
        else:
            logging.info("Config provided, ignoring %s", nettype_setting)

    def _process_monitor(self):
        if not self.options.vt_config:
            if self.options.vt_monitor == 'qmp':
                self.cartesian_parser.assign("monitors", "qmp1")
                self.cartesian_parser.assign("monitor_type_qmp1", "qmp")
        else:
            logging.info("Config provided, ignoring monitor setting")

    def _process_smp(self):
        smp_setting = 'config vt.qemu.smp'
        if not self.options.vt_config:
            if self.options.vt_smp == '1':
                self.cartesian_parser.only_filter("up")
            elif self.options.vt_smp == '2':
                self.cartesian_parser.only_filter("smp2")
            else:
                try:
                    self.cartesian_parser.only_filter("up")
                    self.cartesian_parser.assign(
                        "smp", int(self.options.vt_smp))
                except ValueError:
                    raise ValueError("Invalid %s '%s'. Valid value: (1, 2)" %
                                     self.options.vt_smp)
        else:
            logging.info("Config provided, ignoring %s", smp_setting)

    def _process_arch(self):
        arch_setting = "option --vt-arch or config vt.common.arch"
        if self.options.vt_arch is None:
            pass
        elif not self.options.vt_config:
            self.cartesian_parser.only_filter(self.options.vt_arch)
        else:
            logging.info("Config provided, ignoring %s", arch_setting)

    def _process_machine_type(self):
        machine_type_setting = ("option --vt-machine-type or config "
                                "vt.common.machine_type")
        if not self.options.vt_config:
            if self.options.vt_machine_type is None:
                # TODO: this is x86-specific, instead we can get the default
                # arch from qemu binary and run on all supported machine types
                if ((self.options.vt_arch is None) and
                        (self.options.vt_guest_os is None)):
                    self.cartesian_parser.only_filter(
                        defaults.DEFAULT_MACHINE_TYPE)
            else:
                self.cartesian_parser.only_filter(self.options.vt_machine_type)
        else:
            logging.info("Config provided, ignoring %s", machine_type_setting)

    def _process_image_type(self):
        image_type_setting = 'config vt.qemu.image_type'
        if not self.options.vt_config:
            if self.options.vt_image_type in SUPPORTED_IMAGE_TYPES:
                self.cartesian_parser.only_filter(self.options.vt_image_type)
            else:
                self.cartesian_parser.only_filter("raw")
                # The actual param name is image_format.
                self.cartesian_parser.assign("image_format",
                                             self.options.vt_image_type)
        else:
            logging.info("Config provided, ignoring %s", image_type_setting)

    def _process_nic_model(self):
        nic_model_setting = 'config vt.qemu.nic_model'
        if not self.options.vt_config:
            if self.options.vt_nic_model in SUPPORTED_NIC_MODELS:
                self.cartesian_parser.only_filter(self.options.vt_nic_model)
            else:
                self.cartesian_parser.only_filter("nic_custom")
                self.cartesian_parser.assign(
                    "nic_model", self.options.vt_nic_model)
        else:
            logging.info("Config provided, ignoring %s", nic_model_setting)

    def _process_disk_buses(self):
        disk_bus_setting = 'config vt.qemu.disk_bus'
        if not self.options.vt_config:
            if self.options.vt_disk_bus in SUPPORTED_DISK_BUSES:
                self.cartesian_parser.only_filter(self.options.vt_disk_bus)
            else:
                raise ValueError("Invalid %s '%s'. Valid values: %s" %
                                 (disk_bus_setting,
                                  self.options.vt_disk_bus,
                                  SUPPORTED_DISK_BUSES))
        else:
            logging.info("Config provided, ignoring %s", disk_bus_setting)

    def _process_vhost(self):
        nettype_setting = 'config vt.qemu.nettype'
        vhost_setting = 'config vt.qemu.vhost'
        if not self.options.vt_config:
            if self.options.vt_nettype == "bridge":
                if self.options.vt_vhost == "on":
                    self.cartesian_parser.assign("vhost", "on")
                elif self.options.vt_vhost == "force":
                    self.cartesian_parser.assign("netdev_extra_params",
                                                 '",vhostforce=on"')
                    self.cartesian_parser.assign("vhost", "on")
            else:
                if self.options.vt_vhost in ["on", "force"]:
                    raise ValueError("%s '%s' is incompatible with %s '%s'"
                                     % (nettype_setting,
                                        self.options.vt_nettype,
                                        vhost_setting,
                                        self.options.vt_vhost))
        else:
            logging.info("Config provided, ignoring %s", vhost_setting)

    def _process_qemu_sandbox(self):
        sandbox_setting = 'config vt.qemu.sandbox'
        if not self.options.vt_config:
            if self.options.vt_qemu_sandbox == "off":
                self.cartesian_parser.assign("qemu_sandbox", "off")
        else:
            logging.info("Config provided, ignoring %s", sandbox_setting)

    def _process_qemu_defconfig(self):
        defconfig_setting = 'config vt.qemu.sandbox'
        if not self.options.vt_config:
            if self.options.vt_qemu_defconfig == "no":
                self.cartesian_parser.assign("defconfig", "no")
        else:
            logging.info("Config provided, ignoring %s", defconfig_setting)

    def _process_malloc_perturb(self):
        self.cartesian_parser.assign("malloc_perturb",
                                     self.options.vt_malloc_perturb)

    def _process_qemu_specific_options(self):
        """
        Calls for processing all options specific to the qemu test.

        This method modifies the cartesian set by parsing additional lines.
        """

        self._process_qemu_bin()
        self._process_qemu_accel()
        self._process_monitor()
        self._process_smp()
        self._process_image_type()
        self._process_nic_model()
        self._process_disk_buses()
        self._process_vhost()
        self._process_malloc_perturb()
        self._process_qemu_sandbox()

    def _process_lvsb_specific_options(self):
        """
        Calls for processing all options specific to lvsb test
        """
        self.options.no_downloads = True

    def _process_libvirt_specific_options(self):
        """
        Calls for processing all options specific to libvirt test.
        """
        uri_setting = 'config vt.libvirt.connect_uri'
        if self.options.vt_connect_uri:
            driver_found = False
            for driver in SUPPORTED_LIBVIRT_DRIVERS:
                if self.options.vt_connect_uri.count(driver):
                    driver_found = True
                    self.cartesian_parser.only_filter(driver)
            if not driver_found:
                raise ValueError("Unsupported %s '%s'"
                                 % (uri_setting, self.options.vt_connect_uri))
        else:
            self.cartesian_parser.only_filter("qemu")

    def _process_guest_os(self):
        guest_os_setting = 'option --vt-guest-os'
        if not self.options.vt_config:
            if len(standalone_test.get_guest_name_list(self.options)) == 0:
                raise ValueError("%s '%s' is not on the known guest os for "
                                 "arch '%s' and machine type '%s'. (see "
                                 "--vt-list-guests)"
                                 % (guest_os_setting, self.options.vt_guest_os,
                                    self.options.vt_arch,
                                    self.options.vt_machine_type))
            self.cartesian_parser.only_filter(
                self.options.vt_guest_os or defaults.DEFAULT_GUEST_OS)
        else:
            logging.info("Config provided, ignoring %s", guest_os_setting)

    def _process_restart_vm(self):
        if not self.options.vt_config:
            if not self.options.vt_keep_guest_running:
                self.cartesian_parser.assign("kill_vm", "yes")

    def _process_restore_image_between_tests(self):
        if not self.options.vt_config:
            if not self.options.vt_keep_image_between_tests:
                self.cartesian_parser.assign("restore_image", "yes")

    def _process_mem(self):
        self.cartesian_parser.assign("mem", self.options.vt_mem)

    def _process_tcpdump(self):
        """
        Verify whether we can run tcpdump. If we can't, turn it off.
        """
        try:
            tcpdump_path = utils_misc.find_command('tcpdump')
        except ValueError:
            tcpdump_path = None

        non_root = os.getuid() != 0

        if tcpdump_path is None or non_root:
            self.cartesian_parser.assign("run_tcpdump", "no")

    def _process_no_filter(self):
        if not self.options.vt_config:
            if self.options.vt_no_filter:
                no_filter = ", ".join(self.options.vt_no_filter.split(' '))
                self.cartesian_parser.no_filter(no_filter)

    def _process_only_type_specific(self):
        if not self.options.vt_config:
            if self.options.vt_type_specific:
                self.cartesian_parser.only_filter("(subtest=type_specific)")

    def _process_general_options(self):
        """
        Calls for processing all generic options.

        This method modifies the cartesian set by parsing additional lines.
        """
        self._process_guest_os()
        self._process_arch()
        self._process_machine_type()
        self._process_restart_vm()
        self._process_restore_image_between_tests()
        self._process_mem()
        self._process_tcpdump()
        self._process_no_filter()
        self._process_qemu_img()
        self._process_bridge_mode()
        self._process_only_type_specific()

    def _process_options(self):
        """
        Process the options given in the command line.
        """
        cfg = None
        vt_type_setting = 'option --vt-type'
        vt_config_setting = 'option --vt-config'
        if (not self.options.vt_type) and (not self.options.vt_config):
            raise ValueError("No %s or %s specified" %
                             (vt_type_setting, vt_config_setting))

        if self.options.vt_type:
            if self.options.vt_type not in SUPPORTED_TEST_TYPES:
                raise ValueError("Invalid %s %s. Valid values: %s. "
                                 % (vt_type_setting,
                                    self.options.vt_type,
                                    " ".join(SUPPORTED_TEST_TYPES)))

        self.cartesian_parser = cartesian_config.Parser(debug=False)

        if self.options.vt_config:
            cfg = os.path.abspath(self.options.vt_config)

        if not self.options.vt_config:
            cfg = data_dir.get_backend_cfg_path(self.options.vt_type,
                                                'tests.cfg')

        self.cartesian_parser.parse_file(cfg)
        if self.options.vt_type != 'lvsb':
            self._process_general_options()

        if self.options.vt_type == 'qemu':
            self._process_qemu_specific_options()
        elif self.options.vt_type == 'lvsb':
            self._process_lvsb_specific_options()
        elif self.options.vt_type == 'openvswitch':
            self._process_qemu_specific_options()
        elif self.options.vt_type == 'libvirt':
            self._process_libvirt_specific_options()

    def get_parser(self):
        self._process_options()
        return self.cartesian_parser


class VirtTestCompatPlugin(plugin.Plugin):

    """
    Avocado VT - legacy virt-test support
    """

    name = 'vt'
    enabled = True
    configured = False
    parser = None
    priority = 1

    def configure(self, parser):
        """
        Add the subparser for the run action.

        :param parser: Main test runner parser.
        """
        self.parser = parser

        try:
            qemu_bin_path = standalone_test.find_default_qemu_paths()[0]
        except ValueError:
            qemu_bin_path = "Could not find one"

        qemu_nw_msg = "QEMU network option (%s). " % ", ".join(
            SUPPORTED_NET_TYPES)
        qemu_nw_msg += "Default: user"

        vt_compat_group_setup = parser.runner.add_argument_group(
            'Virt-Test compat layer - VM Setup options')
        vt_compat_group_common = parser.runner.add_argument_group(
            'Virt-Test compat layer - Common options')
        vt_compat_group_qemu = parser.runner.add_argument_group(
            'Virt-Test compat layer - QEMU options')
        vt_compat_group_libvirt = parser.runner.add_argument_group(
            'Virt-Test compat layer - Libvirt options')

        current_run_setup = settings.get_value(
            'vt.setup', 'run_setup', key_type=bool)

        vt_compat_group_setup.add_argument("--vt-setup", action="store_true",
                                           dest="vt_setup",
                                           default=current_run_setup,
                                           help="Run virt test setup actions "
                                                "(restore JeOS image from "
                                                "pristine). Current: %s" %
                                                current_run_setup)

        vt_compat_group_common.add_argument("--vt-config", action="store",
                                            dest="vt_config",
                                            help=("Explicitly choose a "
                                                  "cartesian config. "
                                                  "When choosing this, "
                                                  "some options will be "
                                                  "ignored (see options "
                                                  "below)"))
        vt_compat_group_common.add_argument("--vt-type", action="store",
                                            dest="vt_type",
                                            help=("Choose test type (%s). "
                                                  "Default: qemu" %
                                                  ", ".join(
                                                      SUPPORTED_TEST_TYPES)),
                                            default='qemu')
        arch = settings.get_value('vt.common', 'arch', default=None)
        vt_compat_group_common.add_argument("--vt-arch",
                                            help="Choose the VM architecture. "
                                            "Default: %s" % arch,
                                            default=arch)
        machine = settings.get_value('vt.common', 'machine_type',
                                     default=defaults.DEFAULT_MACHINE_TYPE)
        vt_compat_group_common.add_argument("--vt-machine-type",
                                            help="Choose the VM machine type. "
                                            "Default: %s" % machine,
                                            default=machine)
        vt_compat_group_common.add_argument("--vt-guest-os", action="store",
                                            dest="vt_guest_os",
                                            default=defaults.DEFAULT_GUEST_OS,
                                            help=("Select the guest OS to "
                                                  "be used. If --vt-config is "
                                                  "provided, this will be "
                                                  "ignored. Default: %s" %
                                                  defaults.DEFAULT_GUEST_OS))
        vt_compat_group_common.add_argument("--vt-no-filter", action="store",
                                            dest="vt_no_filter", default="",
                                            help=("List of space separated "
                                                  "'no' filters to be passed "
                                                  "to the config parser. "
                                                  "If --vt-config is "
                                                  "provided, this will be "
                                                  "ignored. Default: ''"))
        qemu_bin_path_current = settings.get_value('vt.qemu', 'qemu_bin',
                                                   default=qemu_bin_path)
        vt_compat_group_qemu.add_argument("--vt-qemu-bin", action="store",
                                          dest="vt_qemu_bin",
                                          default=qemu_bin_path_current,
                                          help=("Path to a custom qemu binary "
                                                "to be tested. If --vt-config "
                                                "is provided and this flag is "
                                                "omitted, no attempt to set "
                                                "the qemu binaries will be "
                                                "made. Current: %s" %
                                                qemu_bin_path_current))
        qemu_dst_bin_path_current = settings.get_value('vt.qemu',
                                                       'qemu_dst_bin',
                                                       default=qemu_bin_path)
        vt_compat_group_qemu.add_argument("--vt-qemu-dst-bin", action="store",
                                          dest="vt_dst_qemu_bin",
                                          default=qemu_dst_bin_path_current,
                                          help=("Path to a custom qemu binary "
                                                "to be tested for the "
                                                "destination of a migration, "
                                                "overrides --vt-qemu-bin. "
                                                "If --vt-config is provided "
                                                "and this flag is omitted, "
                                                "no attempt to set the qemu "
                                                "binaries will be made. "
                                                "Current: %s" %
                                                qemu_dst_bin_path_current))
        supported_uris = ", ".join(SUPPORTED_LIBVIRT_URIS)
        uri_current = settings.get_value('vt.libvirt', 'connect_uri',
                                         default=None)
        vt_compat_group_libvirt.add_argument("--vt-connect-uri",
                                             action="store",
                                             dest="vt_connect_uri",
                                             default=uri_current,
                                             help=("Choose test connect uri "
                                                   "for libvirt (E.g: %s). "
                                                   "Current: %s" %
                                                   (supported_uris,
                                                    uri_current)))

        self.configured = True

    def activate(self, args):
        """
        Run test modules or simple tests.

        :param args: Command line args received from the run subparser.
        """
        from ..loader import loader
        loader.register_plugin(VirtTestLoader)
        if getattr(args, 'vt_setup', False):
            self.parser.application.set_defaults(vt_result=VirtTestResult)
