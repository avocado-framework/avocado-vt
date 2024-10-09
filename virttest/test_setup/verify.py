from virttest import utils_misc
from virttest.test_setup.core import Setuper


class VerifyHostDMesg(Setuper):
    def setup(self):
        # Check host for any errors to start with and just report and
        # clear it off, so that we do not get the false test failures.
        if self.params.get("verify_host_dmesg", "yes") == "yes":
            utils_misc.verify_dmesg(ignore_result=True)

    def cleanup(self):
        if self.params.get("verify_host_dmesg", "yes") == "yes":
            dmesg_log_file = self.params.get("host_dmesg_logfile", "host_dmesg.log")
            level = self.params.get("host_dmesg_level", 3)
            expected_host_dmesg = self.params.get("expected_host_dmesg", "")
            ignore_result = self.params.get("host_dmesg_ignore", "no") == "yes"
            dmesg_log_file = utils_misc.get_path(self.test.debugdir, dmesg_log_file)
            # exception will be propagated so setup_manager handles it instead
            utils_misc.verify_dmesg(
                dmesg_log_file=dmesg_log_file,
                ignore_result=ignore_result,
                level_check=level,
                expected_dmesg=expected_host_dmesg,
            )
