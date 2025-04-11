import glob
import os
import re
import sys

if sys.version_info[:2] == (2, 6):
    import unittest2 as unittest
else:
    import unittest

from virttest import cartesian_config

BASEDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RHELDIR = os.path.join(BASEDIR, "shared", "cfg", "guest-os", "Linux", "RHEL")
UNATTENDEDDIR = os.path.join(BASEDIR, "shared", "unattended")


class CartesianCfgLint(unittest.TestCase):
    @staticmethod
    def get_cfg_as_dict(path, drop_only=True, drop_conditional_assigment=True):
        """
        Gets a single config file as dict

        By putting the content of file within a "variants:" context.

        Optionally (default) also drops all instances of "only" statements,
        and optional assignments, ie:

        section_name:
           foo = bar

        since the files are evaluated individually and that can lead to an
        empty results.
        """
        lines = open(path).readlines()
        if drop_only:
            lines = [l for l in lines if not re.match("^\s*only\s+", l)]
        if drop_conditional_assigment:
            lines = [
                l for l in lines if not re.match("^\s*[a-zA-Z0-9_]+([\s,])?.*\:$", l)
            ]
        lines.insert(0, "variants:")
        content = "\n".join(lines)
        parser = cartesian_config.Parser()
        parser.parse_string(content)
        dicts = [d for d in parser.get_dicts()]
        len_dicts = len(dicts)
        assert len_dicts == 1
        return dicts[0]

    @unittest.skipIf(
        not os.path.isdir(RHELDIR), "Could not find RHEL configuration dir"
    )
    def test_rhel_iso_names(self):
        arch_map = {
            "i386": "32",
            "x86_64": "64",
            "ppc64": "ppc64",
            "ppc64le": "ppc64le",
            "aarch64": "aarch64",
        }

        for major in (5, 6, 7):
            minors = set(
                [
                    ver.split(".")[1]
                    for ver in glob.glob(os.path.join(RHELDIR, "%s.*" % major))
                ]
            )
            for minor in minors:
                if minor == "devel":
                    continue
                generic_cfg = "%s.%s.cfg" % (major, minor)
                generic_cfg_path = os.path.join(RHELDIR, generic_cfg)
                config_dict = self.get_cfg_as_dict(generic_cfg_path)
                self.assertEqual(config_dict["shortname"], "%s.%s" % (major, minor))
                self.assertEqual(
                    config_dict["image_name"], "images/rhel%s%s" % (major, minor)
                )
                for arch, alt in list(arch_map.items()):
                    arch_cfg = "%s.%s/%s.cfg" % (major, minor, arch)
                    arch_cfg_path = os.path.join(RHELDIR, arch_cfg)
                    if not os.path.exists(arch_cfg_path):
                        continue
                    config_dict = self.get_cfg_as_dict(arch_cfg_path)
                    if "cdrom_unattended" in config_dict:
                        self.assertEqual(
                            config_dict["cdrom_unattended"],
                            "images/rhel%s%s-%s/ks.iso" % (major, minor, alt),
                        )
                    if "kernel" in config_dict:
                        self.assertEqual(
                            config_dict["kernel"],
                            "images/rhel%s%s-%s/vmlinuz" % (major, minor, alt),
                        )
                    if "initrd" in config_dict:
                        self.assertEqual(
                            config_dict["initrd"],
                            "images/rhel%s%s-%s/initrd.img" % (major, minor, alt),
                        )
                    if "cdrom_cd1" in config_dict:
                        self.assertEqual(
                            config_dict["cdrom_cd1"],
                            "isos/linux/RHEL-%s.%s-%s-DVD.iso" % (major, minor, arch),
                        )

    @unittest.skipIf(
        not os.path.isdir(UNATTENDEDDIR), "Could not find unattended configuration dir"
    )
    def test_unattended_kickstart_password_123456(self):
        """
        Tests if passwords in unattended installs are set to 123456
        """
        rootpw_regex = re.compile(
            r"^rootpw\s+(--plaintext\s+)?123456\s?$", re.MULTILINE
        )
        for ks in glob.glob(os.path.join(UNATTENDEDDIR, "*.ks")):
            self.assertIsNotNone(rootpw_regex.search(open(ks).read()))
