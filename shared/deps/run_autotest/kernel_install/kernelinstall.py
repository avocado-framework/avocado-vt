import os
import logging
import sys

from autotest.client import test
from autotest.client import utils
from autotest.client.shared import git, error, software_manager


class kernelinstall(test.test):
    version = 1
    sm = software_manager.SoftwareManager()

    def _kernel_install_rpm(self, rpm_file, kernel_deps_rpms=None,
                            need_reboot=True):
        """
        Install kernel rpm package.
        The rpm packages should be a url or put in this test's
        directory (client/test/kernelinstall)
        """
        if kernel_deps_rpms:
            logging.info("Installing kernel dependencies.")
            if isinstance(kernel_deps_rpms, list):
                kernel_deps_rpms = " ".join(kernel_deps_rpms)
            self.sm.install(kernel_deps_rpms)

        dst = os.path.join("/tmp", os.path.basename(rpm_file))
        knl = utils.get_file(rpm_file, dst)
        kernel = self.job.kernel(knl)
        logging.info("Installing kernel %s", rpm_file)
        kernel.install(install_vmlinux=False)

        if need_reboot:
            kernel.boot()
        else:
            kernel.add_to_bootloader()

    def _kernel_install_koji(self, kernel_koji_spec, kernel_deps_koji_spec,
                             need_reboot=True):
        # Using hardcoded package names (the names are not expected to change)
        # we avoid lookup errors due to SSL problems, so let's go with that.
        for koji_package in ['koji', 'brewkoji']:
            if not self.sm.check_installed(koji_package):
                logging.debug("%s missing - trying to install", koji_package)
                self.sm.install(koji_package)

        sys.path.append(self.bindir)
        try:
            from staging import utils_koji
        except ImportError:
            from autotest.client.shared import utils_koji
        # First, download packages via koji/brew
        c = utils_koji.KojiClient()

        deps_rpms = []
        k_dep = utils_koji.KojiPkgSpec(text=kernel_deps_koji_spec)
        logging.info('Fetching kernel dependencies: %s', kernel_deps_koji_spec)
        c.get_pkgs(k_dep, self.bindir)
        rpm_file_name_list = c.get_pkg_rpm_file_names(k_dep)
        if len(rpm_file_name_list) == 0:
            raise error.TestError("No packages on brew/koji match spec %s" %
                                  kernel_deps_koji_spec)
        dep_rpm_basename = rpm_file_name_list[0]
        deps_rpms.append(os.path.join(self.bindir, dep_rpm_basename))

        k = utils_koji.KojiPkgSpec(text=kernel_koji_spec)
        logging.info('Fetching kernel: %s', kernel_koji_spec)
        c.get_pkgs(k, self.bindir)
        rpm_file_name_list = c.get_pkg_rpm_file_names(k)
        if len(rpm_file_name_list) == 0:
            raise error.TestError("No packages on brew/koji match spec %s" %
                                  kernel_koji_spec)

        kernel_rpm_basename = rpm_file_name_list[0]
        kernel_rpm_path = os.path.join(self.bindir, kernel_rpm_basename)

        # Then install kernel rpm packages.
        self._kernel_install_rpm(kernel_rpm_path, deps_rpms, need_reboot)

    def _kernel_install_src(self, base_tree, config=None, config_list=None,
                            patch_list=None, need_reboot=True):
        if not utils.is_url(base_tree):
            base_tree = os.path.join(self.bindir, base_tree)
        if not utils.is_url(config):
            config = os.path.join(self.bindir, config)
        kernel = self.job.kernel(base_tree, self.outputdir)
        if patch_list:
            patches = []
            for p in patch_list.split():
                # Make sure all the patches are in local.
                if not utils.is_url(p):
                    continue
                dst = os.path.join(self.bindir, os.path.basename(p))
                local_patch = utils.get_file(p, dst)
                patches.append(local_patch)
            kernel.patch(*patches)
        if not os.path.isfile(config):
            config = None
        if not config and not config_list:
            kernel.config()
        else:
            kernel.config(config, config_list)
        kernel.build()
        kernel.install()

        if need_reboot:
            kernel.boot()
        else:
            kernel.add_to_bootloader()

    def _kernel_install_git(self, repo, config, repo_base=None,
                            branch="master", commit=None, config_list=None,
                            patch_list=None, need_reboot=True):
        repodir = os.path.join("/tmp", 'kernel_src')
        repodir = git.get_repo(uri=repo, branch=branch,
                               destination_dir=repodir,
                               commit=commit, base_uri=repo_base)
        self._kernel_install_src(repodir, config, config_list, patch_list,
                                 need_reboot)

    def execute(self, install_type="koji", params=None):
        need_reboot = params.get("need_reboot") == "yes"

        logging.info("Chose to install kernel through '%s', proceeding",
                     install_type)

        if install_type == "rpm":
            rpm_url = params.get("kernel_rpm_path")
            kernel_deps_rpms = params.get("kernel_deps_rpms", None)

            self._kernel_install_rpm(rpm_url, kernel_deps_rpms, need_reboot)
        elif install_type in ["koji", "brew"]:

            kernel_koji_spec = params.get("kernel_koji_spec")
            kernel_deps_koji_spec = params.get("kernel_deps_koji_spec")

            self._kernel_install_koji(kernel_koji_spec, kernel_deps_koji_spec,
                                      need_reboot)

        elif install_type == "git":
            repo = params.get('kernel_git_repo')
            repo_base = params.get('kernel_git_repo_base', None)
            branch = params.get('kernel_git_branch', "master")
            commit = params.get('kernel_git_commit', None)
            patch_list = params.get("kernel_patch_list", None)
            config = params.get('kernel_config')
            config_list = params.get("kernel_config_list", None)

            self._kernel_install_git(repo, config, repo_base, branch, commit,
                                     config_list, patch_list, need_reboot)
        elif install_type == "tar":
            src_pkg = params.get("kernel_src_pkg")
            config = params.get('kernel_config')
            patch_list = params.get("kernel_patch_list", None)

            self._kernel_install_src(src_pkg, config, None, patch_list,
                                     need_reboot)
        else:
            logging.error("Could not find '%s' method, "
                          "keep the current kernel.", install_type)
