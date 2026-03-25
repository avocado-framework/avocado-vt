import logging
import os
import re

from avocado.utils import process as a_process
from avocado.utils import service

from virttest import utils_misc
from virttest.test_setup.core import Setuper

LOG = logging.getLogger("avocado." + __name__)


def collect_lcov_coverage(
    build_dir, output_dir, test_name, component, max_name_len=80, extra_opts=""
):
    """
    Collect coverage data using lcov with per-test naming.

    :param build_dir: Build directory containing .gcda files
    :param output_dir: Output directory for coverage files
    :param test_name: Name of the test for tracefile naming
    :param component: Component name (qemu or libvirt)
    :param max_name_len: The max len of test name used in tracefile
    :param extra_opts: Additional lcov command options
    :return: Path to generated tracefile, or None on failure
    """
    if not os.path.isdir(build_dir):
        LOG.warning("%s build directory not found: %s", component, build_dir)
        return None

    os.makedirs(output_dir, exist_ok=True)
    tmp_test_name = test_name
    if len(test_name) > max_name_len:
        match = re.search(r"io-github-autotest-[^.]+\.(.*)", test_name)
        if match:
            short_name = match.group(1)
        else:
            short_name = test_name
        # Ensure short_name + suffix doesn't exceed max_name_len
        # Reserve 9 chars for "_" + 8-char random string
        max_short_len = max_name_len - 9
        if len(short_name) > max_short_len:
            short_name = short_name[:max_short_len]
        tmp_test_name = short_name + "_" + utils_misc.generate_random_string(8)

    tracefile = os.path.join(output_dir, "coverage_%s.info" % tmp_test_name)

    # Collect coverage data with test name
    collect_cmd = (
        "lcov --capture "
        "--directory %s "
        "--output-file %s "
        "--test-name %s %s" % (build_dir, tracefile, test_name, extra_opts)
    )

    try:
        a_process.system(collect_cmd, shell=True)

        # Validate the generated file
        if os.path.exists(tracefile):
            file_size = os.path.getsize(tracefile)
            if file_size > 0:
                LOG.info(
                    "%s coverage tracefile saved: %s (%d bytes)",
                    component.upper(),
                    tracefile,
                    file_size,
                )
                return tracefile
            else:
                LOG.warning(
                    "%s coverage file is empty, removing: %s", component, tracefile
                )
                os.unlink(tracefile)
                return None
        else:
            LOG.warning("%s coverage file was not created: %s", component, tracefile)
            return None

    except Exception as e:
        LOG.error("Failed to collect %s coverage: %s", component, e)
        return None


def collect_gcovr_coverage(build_dir, output_dir, component, cmd_opts="--html"):
    """
    Collect coverage data using gcovr in the specified format.

    :param build_dir: Build directory containing .gcda files
    :param output_dir: Output directory for coverage report
    :param component: Component name (qemu or libvirt)
    :param cmd_opts: Additional gcovr command options
                     (e.g., "--html", "--xml", "--json", "--csv", "--txt")
    :return: Path to generated coverage file, or None on failure
    """
    if not os.path.isdir(build_dir):
        LOG.warning("%s build directory not found: %s", component, build_dir)
        return None

    try:
        # Import here to avoid circular dependencies
        from avocado.utils import cpu as cpu_utils

        os.makedirs(output_dir, exist_ok=True)

        # Map gcovr format flags to output filenames and display names
        format_map = {
            "--txt": ("gcov.txt", "TXT"),
            "--xml": ("gcov.xml", "XML"),
            "--json": ("gcov.json", "JSON"),
            "--markdown": ("gcov.md", "MARKDOWN"),
            "--csv": ("gcov.csv", "CSV"),
            "--clover": ("gcov-clover.xml", "CLOVER"),
            "--cobertura": ("gcov-cobertura.xml", "COBERTURA"),
            "--lcov": ("gcov.lcov", "LCOV"),
            "--sonarqube": ("gcov-sonarqube.xml", "SonarQube XML"),
            "--coveralls": ("gcov-coveralls.json", "Coveralls JSON"),
        }

        output_filename = "gcov.html"
        format_name = "HTML"
        for flag, (filename, name) in format_map.items():
            if flag in cmd_opts:
                output_filename = filename
                format_name = name
                break

        output_file = os.path.join(output_dir, output_filename)

        # Get CPU count for parallel processing
        online_count = (
            cpu_utils.online_count()
            if hasattr(cpu_utils, "online_count")
            else cpu_utils.online_cpus_count()
        )

        # Change to build directory for gcovr
        original_dir = os.getcwd()
        os.chdir(build_dir)

        # Build gcovr command
        collect_cmd = "gcovr -j %s -o %s -s %s ." % (
            online_count,
            output_file,
            cmd_opts,
        )

        LOG.info("Collecting %s %s coverage report...", component.upper(), format_name)
        a_process.system(collect_cmd, shell=True)

        # Restore original directory
        os.chdir(original_dir)

        # Validate the generated file
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            if file_size > 0:
                LOG.info(
                    "%s coverage %s report saved: %s (%d bytes)",
                    component.upper(),
                    format_name,
                    output_file,
                    file_size,
                )
                return output_file
            else:
                LOG.warning(
                    "%s %s report is empty: %s", component, format_name, output_file
                )
                return None
        else:
            LOG.warning(
                "%s %s report was not created: %s", component, format_name, output_file
            )
            return None

    except Exception as e:
        LOG.error("Failed to collect %s gcovr coverage: %s", component, e)
        # Restore directory on error
        try:
            os.chdir(original_dir)
        except Exception:
            pass
        return None


class ResetGCov(Setuper):
    """Reset code coverage data for QEMU and/or libvirt before each test."""

    def setup(self):
        # Check if code coverage for qemu is enabled and
        # if coverage reset is enabled too, reset coverage report
        gcov_qemu = self.params.get("gcov_qemu", "no") == "yes"
        gcov_qemu_reset = self.params.get("gcov_qemu_reset", "no") == "yes"
        if gcov_qemu and gcov_qemu_reset:
            qemu_builddir = self.params.get(
                "gcov_qemu_builddir", os.path.join(self.test.bindir, "build", "qemu")
            )
            qemu_bin = os.path.join(self.test.bindir, "bin", "qemu")
            if os.path.isdir(qemu_builddir) and os.path.isfile(qemu_bin):
                os.chdir(qemu_builddir)
                LOG.info("Resetting QEMU code coverage data")
                # Give write permissions for coverage files
                # (libvirt/qemu process may need write access)
                reset_cmd = "make clean-coverage;%s -version;" % qemu_bin
                reset_cmd += (
                    'find %s -name "*.gcda" -exec chmod a=rwx {} \;' % qemu_builddir
                )
                try:
                    a_process.system(reset_cmd, shell=True)
                    LOG.info("QEMU coverage data reset successfully")
                except Exception as e:
                    LOG.warning("Failed to reset QEMU coverage: %s", e)
                    strict_reset = (
                        self.params.get("gcov_qemu_reset_strict", "yes") == "yes"
                    )
                    if strict_reset:
                        raise e

        # Check if code coverage for libvirt is enabled
        gcov_libvirt = self.params.get("gcov_libvirt", "no") == "yes"
        gcov_libvirt_reset = self.params.get("gcov_libvirt_reset", "no") == "yes"
        if gcov_libvirt and gcov_libvirt_reset:
            libvirt_builddir = self.params.get(
                "gcov_libvirt_builddir", "/var/tmp/libvirt"
            )
            if os.path.isdir(libvirt_builddir):
                LOG.info("Resetting libvirt code coverage data in %s", libvirt_builddir)

                # Find and remove .gcda files
                reset_cmd = 'find %s -name "*.gcda" -type f -delete' % libvirt_builddir

                # Also reset lcov counters if lcov is available
                lcov_reset = (
                    "lcov --zerocounters --directory %s 2>/dev/null || true"
                    % libvirt_builddir
                )

                # Fix permissions for coverage files
                chmod_cmd = (
                    'find %s -name "*.gcda" -o -name "*.gcno" | xargs chmod a+rw 2>/dev/null || true'
                    % libvirt_builddir
                )

                full_reset_cmd = "%s; %s; %s" % (reset_cmd, lcov_reset, chmod_cmd)

                try:
                    a_process.system(full_reset_cmd, shell=True)
                    LOG.info("Libvirt coverage data reset successfully")

                    # Optionally restart libvirt daemon to ensure clean state
                    restart_daemon = (
                        self.params.get("gcov_libvirt_restart_daemon", "no") == "yes"
                    )
                    if restart_daemon:
                        daemon_name = self.params.get(
                            "gcov_libvirt_daemon", "virtqemud"
                        )
                        try:
                            libvirt_service = service.Factory.create_service(
                                daemon_name
                            )
                            libvirt_service.restart()
                            LOG.info(
                                "Restarted %s daemon for clean coverage state",
                                daemon_name,
                            )
                        except Exception as e:
                            LOG.warning("Failed to restart %s: %s", daemon_name, e)

                except Exception as e:
                    LOG.warning("Failed to reset libvirt coverage: %s", e)
                    strict_reset = (
                        self.params.get("gcov_libvirt_reset_strict", "yes") == "yes"
                    )
                    if strict_reset:
                        raise e

    def cleanup(self):
        pass
