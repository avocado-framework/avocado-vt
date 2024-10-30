import os

from avocado.utils import process as a_process

from virttest.test_setup.core import Setuper


class ResetQemuGCov(Setuper):
    def setup(self):
        # Check if code coverage for qemu is enabled and
        # if coverage reset is enabled too, reset coverage report
        gcov_qemu = self.params.get("gcov_qemu", "no") == "yes"
        gcov_qemu_reset = self.params.get("gcov_qemu_reset", "no") == "yes"
        if gcov_qemu and gcov_qemu_reset:
            qemu_builddir = os.path.join(self.test.bindir, "build", "qemu")
            qemu_bin = os.path.join(self.test.bindir, "bin", "qemu")
            if os.path.isdir(qemu_builddir) and os.path.isfile(qemu_bin):
                os.chdir(qemu_builddir)
                # Looks like libvirt process does not have permissions to write to
                # coverage files, hence give write for all files in qemu source
                reset_cmd = "make clean-coverage;%s -version;" % qemu_bin
                reset_cmd += (
                    'find %s -name "*.gcda" -exec chmod a=rwx {} \;' % qemu_builddir
                )
                a_process.system(reset_cmd, shell=True)

    def cleanup(self):
        pass
