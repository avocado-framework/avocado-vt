import re

import unittest.mock

from virttest import utils_disk


LS_BLOCK_OUTPUT = 'lrwxrwxrwx. .../block/sda\n' \
                  'lrwxrwxrwx. .../block/sda/sda1\n' \
                  'lrwxrwxrwx. .../block/sda/sda2\n' \
                  'lrwxrwxrwx. .../block/sdb\n' \
                  'lrwxrwxrwx. .../block/sdc\n' \
                  'lrwxrwxrwx. .../block/sdd\n' \
                  'lrwxrwxrwx. .../block/sdd/sdd1\n' \
                  'lrwxrwxrwx. .../block/sdd/sdd2\n' \
                  'lrwxrwxrwx. .../block/sdd/sdd3\n' \
                  'lrwxrwxrwx. .../block/nvme0n1\n'

LS_BLOCK_SDA1_OUTPUT = 'lrwxrwxrwx. .../block/sda/sda1\n'
LS_BLOCK_SDA2_OUTPUT = 'lrwxrwxrwx. .../block/sda/sda2\n'

LS_BLOCK_SDB1_OUTPUT = 'lrwxrwxrwx. .../block/sdb/sdb1\n'

LS_BLOCK_SDD1_OUTPUT = 'lrwxrwxrwx. .../block/sdd/sdd1\n'
LS_BLOCK_SDD2_OUTPUT = 'lrwxrwxrwx. .../block/sdd/sdd2\n'
LS_BLOCK_SDD3_OUTPUT = 'lrwxrwxrwx. .../block/sdd/sdd3\n'

LS_BLOCK_NVME0N1P1_OUTPUT = 'lrwxrwxrwx. .../block/nvme0n1p1\n'

LSBLK_KNAME_SIZE_SDA_OUTPUT = 'sda    20G\n'
LSBLK_KNAME_SIZE_SDA1_OUTPUT = 'sda1    1G\n'
LSBLK_KNAME_SIZE_SDA2_OUTPUT = 'sda2   19G\n'

LSBLK_KNAME_SIZE_SDB_OUTPUT = 'sdb    30G\n'
LSBLK_KNAME_SIZE_SDB1_OUTPUT = 'sdb1    1G\n'

LSBLK_KNAME_SIZE_SDC_OUTPUT = 'sdc    40G\n'

LSBLK_KNAME_SIZE_SDD_OUTPUT = 'sdd    50G\n'
LSBLK_KNAME_SIZE_SDD1_OUTPUT = 'sdd1    5G\n'
LSBLK_KNAME_SIZE_SDD2_OUTPUT = 'sdd2   15G\n'
LSBLK_KNAME_SIZE_SDD3_OUTPUT = 'sdd3   30G\n'

LSBLK_KNAME_SIZE_NVME0N1_OUTPUT = 'nvme0n1   100G\n'
LSBLK_KNAME_SIZE_NVME0N1P1_OUTPUT = 'nvme0n1p1   80G\n'

LSBLK_KNAME_MOUNTPOINT_OUTPUT = 'sda\n' \
                                'sda1  /boot\n' \
                                'sda2\n' \
                                'sdb\n' \
                                'sdc\n' \
                                'sdd\n' \
                                'sdd1  \n' \
                                'sdd2  \n' \
                                'sdd3  \n' \
                                'nvme0n1  \n' \
                                'dm-0  /\n' \
                                'dm-1  [SWAP]\n'

UDEVADM_SDA_OUTPUT = 'E: DEVTYPE=disk\n' \
                     'E: ID_SERIAL=drive_image1\n'
UDEVADM_SDA1_OUTPUT = 'E: DEVTYPE=partition\n' \
                      'E: ID_SERIAL=drive_image1\n'
UDEVADM_SDA2_OUTPUT = 'E: DEVTYPE=partition\n' \
                      'E: ID_SERIAL=drive_image1\n'


UDEVADM_SDB_OUTPUT = 'E: DEVTYPE=disk\n' \
                     'E: ID_SERIAL=drive_image2\n' \
                     'E: ID_WWN=0x600508b1001ccccc\n'

UDEVADM_SDB1_OUTPUT = 'E: DEVTYPE=partition\n' \
                      'E: ID_SERIAL=drive_image2\n' \
                      'E: ID_WWN=0x600508b1001ccccc\n'

UDEVADM_SDC_OUTPUT = 'E: DEVTYPE=disk\n' \
                     'E: ID_SERIAL=drive_image3\n' \
                     'E: ID_WWN=0x600508b1001fffff\n'

UDEVADM_SDD_OUTPUT = 'E: DEVTYPE=disk\n' \
                     'E: ID_SERIAL=drive_image4\n'
UDEVADM_SDD1_OUTPUT = 'E: DEVTYPE=partition\n' \
                      'E: ID_SERIAL=drive_image4\n'
UDEVADM_SDD2_OUTPUT = 'E: DEVTYPE=partition\n' \
                      'E: ID_SERIAL=drive_image4\n'
UDEVADM_SDD3_OUTPUT = 'E: DEVTYPE=partition\n' \
                      'E: ID_SERIAL=drive_image4\n'

UDEVADM_NVME0N1_OUTPUT = 'E: DEVTYPE=disk\n' \
                         'E: ID_SERIAL=drive_image5\n'
UDEVADM_NVME0N1P1_OUTPUT = 'E: DEVTYPE=partition\n' \
                           'E: ID_SERIAL=drive_image5\n'

MOUNT_INFO = 'sysfs /sys sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0\n' \
             'proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0\n' \
             'tmpfs /dev/shm tmpfs rw,seclabel,nosuid,nodev 0 0\n' \
             '/dev/mapper/rhel_bootp--73--5--236-root ... 0 0\n' \
             '/dev/sda1 /boot xfs rw,seclabel,relatime,attr2,inode64 0 0\n' \
             'tmpfs /run/user/0 tmpfs rw,seclabel,mode=700 0 0\n' \
             'gvfsd-fuse /run/user/0/gvfs fuse.gvfsd-fuse rw,group_id=0 0 0\n' \
             'fusectl /sys/fs/fuse/connections fusectl rw,relatime 0 0\n' \

MOUNT_INFO_SDB1 = '/dev/sdb1 /mnt/sdb1 ext4 rw,seclabel,relatime,attr2,inode64 0 0\n'
MOUNT_INFO_SDA1 = '/dev/sda1 /boot xfs rw,seclabel,relatime,attr2,inode64 0 0\n'

LIST_DISK0_PARTS = '  Partition ###  Type              Size     Offset \n' \
                   '  -------------  ----------------  -------  -------\n' \
                   '  Partition 1    Primary            300 MB  1024 KB\n' \
                   '  Partition 2    Primary             29 GB   301 MB\n'

LIST_DISK1_PARTS = 'There are no partitions on this disk to show.\n'

LIST_DISK1_PART1 = '  Partition ###  Type              Size     Offset \n' \
                   '  -------------  ----------------  -------  -------\n' \
                   '* Partition 1    Primary           1024 MB  1024 KB\n'

EXPACTED_DISKS = {
    'sda': ['sda', '20G', 'disk', 'drive_image1', None],
    'sda1': ['sda1', '1G', 'partition', 'drive_image1', None],
    'sda2': ['sda2', '19G', 'partition', 'drive_image1', None],
    'sdb': ['sdb', '30G', 'disk', 'drive_image2', '0x600508b1001ccccc'],
    'sdc': ['sdc', '40G', 'disk', 'drive_image3', '0x600508b1001fffff'],
    'sdd': ['sdd', '50G', 'disk', 'drive_image4', None],
    'sdd1': ['sdd1', '5G', 'partition', 'drive_image4', None],
    'sdd2': ['sdd2', '15G', 'partition', 'drive_image4', None],
    'sdd3': ['sdd3', '30G', 'partition', 'drive_image4', None],
    'nvme0n1': ['nvme0n1', '100G', 'disk', 'drive_image5', None]
}


def wrap_windows_cmd(cmd, did=None):
    disk = "disk_xUJd"
    cmd_header = "echo list disk > " + disk
    cmd_header += " && echo select disk %s >> " + disk
    if did is not None:
        cmd_header %= did
    cmd_footer = " echo exit >> " + disk
    cmd_footer += " && diskpart /s " + disk
    cmd_footer += " && del /f " + disk
    cmd_list = []
    for i in cmd.split(";"):
        i += " >> " + disk
        cmd_list.append(i)
    cmd = " && ".join(cmd_list)
    return " && ".join([cmd_header, cmd, cmd_footer])


class FakeSession(object):
    def __init__(self):
        self.lsblk_kname_size_cmd = 'lsblk -o KNAME,SIZE | grep "%s "'
        self.ls_block_cmd = 'ls /sys/dev/block -l | grep "/pci"'
        self.udevadm_cmd = 'udevadm info -q all -n %s'
        self.cmd_mapping = {
            self.ls_block_cmd: LS_BLOCK_OUTPUT,
            self.lsblk_kname_size_cmd % 'sda': LSBLK_KNAME_SIZE_SDA_OUTPUT,
            self.lsblk_kname_size_cmd % 'sda1': LSBLK_KNAME_SIZE_SDA1_OUTPUT,
            self.lsblk_kname_size_cmd % 'sda2': LSBLK_KNAME_SIZE_SDA2_OUTPUT,
            self.lsblk_kname_size_cmd % 'sdb': LSBLK_KNAME_SIZE_SDB_OUTPUT,
            self.lsblk_kname_size_cmd % 'sdc': LSBLK_KNAME_SIZE_SDC_OUTPUT,
            self.lsblk_kname_size_cmd % 'sdd': LSBLK_KNAME_SIZE_SDD_OUTPUT,
            self.lsblk_kname_size_cmd % 'sdd1': LSBLK_KNAME_SIZE_SDD1_OUTPUT,
            self.lsblk_kname_size_cmd % 'sdd2': LSBLK_KNAME_SIZE_SDD2_OUTPUT,
            self.lsblk_kname_size_cmd % 'sdd3': LSBLK_KNAME_SIZE_SDD3_OUTPUT,
            self.lsblk_kname_size_cmd % 'nvme0n1': LSBLK_KNAME_SIZE_NVME0N1_OUTPUT,
            self.udevadm_cmd % 'sda': UDEVADM_SDA_OUTPUT,
            self.udevadm_cmd % 'sda1': UDEVADM_SDA1_OUTPUT,
            self.udevadm_cmd % 'sda2': UDEVADM_SDA2_OUTPUT,
            self.udevadm_cmd % 'sdb': UDEVADM_SDB_OUTPUT,
            self.udevadm_cmd % 'sdc': UDEVADM_SDC_OUTPUT,
            self.udevadm_cmd % 'sdd': UDEVADM_SDD_OUTPUT,
            self.udevadm_cmd % 'sdd1': UDEVADM_SDD1_OUTPUT,
            self.udevadm_cmd % 'sdd2': UDEVADM_SDD2_OUTPUT,
            self.udevadm_cmd % 'sdd3': UDEVADM_SDD3_OUTPUT,
            self.udevadm_cmd % 'nvme0n1': UDEVADM_NVME0N1_OUTPUT
        }

        self.lsblk_kname_mp_cmd = 'lsblk -o KNAME,MOUNTPOINT'
        self.lsblk_kname_mp_output = LSBLK_KNAME_MOUNTPOINT_OUTPUT
        self.ls_block_output = LS_BLOCK_OUTPUT

        self.mount_list_cmd = 'cat /proc/mounts'
        self.mount_sdb1_cmd = 'mount -t ext4 /dev/sdb1 /mnt/sdb1'
        self.mount_info = MOUNT_INFO
        self.umount_sda1_cmd = "umount /boot"

        self.create_disk1_part_cmd = wrap_windows_cmd(
                " echo create partition primary size=1024; echo list partition", '1')

        self.parted_mkpart_sdb1_cmd = 'parted -s "/dev/sdb" mkpart primary 0M 1024.0M'
        self.parted_mkpart_nvme0n1p1_cmd = 'parted -s "/dev/nvme0n1" mkpart primary 0M 81920.0M'
        self.parted_print_sdd_cmd = "parted -s /dev/sdd print|awk '/^ / {print $1}'"
        _ = (_.group(1) for _ in re.finditer(r'sdd(\d+)', self.lsblk_kname_mp_output, re.M))
        self.parted_print_sdd_ouput = '\n'.join(_) + '\n'
        self.parted_print_nvme0n1_cmd = "parted -s /dev/nvme0n1 print|awk '/^ / {print $1}'"
        self.parted_print_nvme0n1_ouput = '1\n'
        self.parted_rm_sda1_cmd = 'parted -s "/dev/sda" rm sda1'
        self.parted_rm_sda2_cmd = 'parted -s "/dev/sda" rm sda2'
        self.parted_rm_nvme0n1p1_cmd = 'parted -s "/dev/nvme0n1" rm 1'
        self.parted_rm_sdd1_cmd = 'parted -s "/dev/sdd" rm 1'
        self.parted_rm_sdd2_cmd = 'parted -s "/dev/sdd" rm 2'
        self.parted_rm_sdd3_cmd = 'parted -s "/dev/sdd" rm 3'

        self.parted_rm_mapping = {
            self.parted_rm_sda1_cmd: ['sda1', LS_BLOCK_SDA1_OUTPUT],
            self.parted_rm_sda2_cmd: ['sda2', LS_BLOCK_SDA2_OUTPUT],
            self.parted_rm_sdd1_cmd: ['sdd1', LS_BLOCK_SDD1_OUTPUT],
            self.parted_rm_sdd2_cmd: ['sdd2', LS_BLOCK_SDD2_OUTPUT],
            self.parted_rm_sdd3_cmd: ['sdd3', LS_BLOCK_SDD3_OUTPUT],
            self.parted_rm_nvme0n1p1_cmd: ['nvme0n1p1', LS_BLOCK_NVME0N1P1_OUTPUT],
        }

        self.parted_mkpart_mapping = {
            self.parted_mkpart_sdb1_cmd: ['sdb1', LS_BLOCK_SDB1_OUTPUT,
                                          LSBLK_KNAME_SIZE_SDB1_OUTPUT,
                                          UDEVADM_SDB1_OUTPUT],
            self.parted_mkpart_nvme0n1p1_cmd: ['nvme0n1p1',
                                               LS_BLOCK_NVME0N1P1_OUTPUT,
                                               LSBLK_KNAME_SIZE_NVME0N1P1_OUTPUT,
                                               UDEVADM_NVME0N1P1_OUTPUT],
        }

        self.create_part_mapping = {
            self.create_disk1_part_cmd: [LIST_DISK1_PART1]
        }

        self.parted_print_mapping = {
            self.parted_print_sdd_cmd: [self.parted_print_sdd_ouput],
            self.parted_print_nvme0n1_cmd: [self.parted_print_nvme0n1_ouput]
        }

        self.mount_mapping = {
            self.mount_sdb1_cmd: [MOUNT_INFO_SDB1]
        }

        self.umount_mapping = {
            self.umount_sda1_cmd: [MOUNT_INFO_SDA1]
        }

    def parted_mkpart(self, cmd):
        val = self.parted_mkpart_mapping[cmd]
        self.cmd_mapping[self.ls_block_cmd] = self.ls_block_output + val[1]
        self.cmd_mapping[self.lsblk_kname_size_cmd % val[0]] = val[2]
        self.cmd_mapping[self.udevadm_cmd % val[0]] = val[3]
        self.ls_block_output = self.cmd_mapping[self.ls_block_cmd]

    def parted_rm(self, cmd):
        val = self.parted_rm_mapping[cmd]
        self.ls_block_output = self.ls_block_output.replace(val[1], '')
        self.cmd_mapping[self.ls_block_cmd] = self.ls_block_output
        del self.cmd_mapping[self.lsblk_kname_size_cmd % val[0]]
        del self.cmd_mapping[self.udevadm_cmd % val[0]]

    def parted_print(self, cmd):
        return self.parted_print_mapping[cmd][0]

    def mount(self, cmd):
        self.mount_info = self.mount_info + self.mount_mapping[cmd][0]

    def umount(self, cmd):
        val = self.umount_mapping[cmd]
        self.mount_info = self.mount_info.replace(val[0], '')

    def create_part(self, cmd):
        return self.create_part_mapping[cmd][0]

    def cmd(self, cmd, timeout=60):
        if cmd in self.parted_mkpart_mapping:
            self.parted_mkpart(cmd)
            return
        if cmd in self.create_part_mapping:
            return self.create_part(cmd)
        if cmd == self.ls_block_cmd:
            return self.ls_block_output
        if cmd == self.lsblk_kname_mp_cmd:
            return self.lsblk_kname_mp_output
        if cmd in self.parted_rm_mapping:
            self.parted_rm(cmd)
            return
        if cmd == self.ls_block_cmd:
            return self.ls_block_output
        if cmd in self.cmd_mapping:
            return self.cmd_mapping.get(cmd)

    def cmd_output(self, cmd, tiemout=60):
        if cmd == self.lsblk_kname_mp_cmd:
            return self.lsblk_kname_mp_output
        if cmd in self.parted_print_mapping:
            return self.parted_print(cmd)

    def cmd_output_safe(self, cmd):
        if cmd == self.mount_list_cmd:
            return self.mount_info

    def cmd_status(self, cmd, safe=True, timeout=60):
        if cmd in self.mount_mapping:
            self.mount(cmd)
            return 0
        if cmd in self.umount_mapping:
            self.umount(cmd)
            return 0


class TestUtilsDisk(unittest.TestCase):
    def setUp(self):
        self.expected_disks = EXPACTED_DISKS.copy()

    def test_get_linux_disks(self):
        session = FakeSession()
        self.assertDictEqual(
                utils_disk.get_linux_disks(session), {'sdb': self.expected_disks['sdb'],
                                                      'sdc': self.expected_disks['sdc'],
                                                      'nvme0n1': self.expected_disks['nvme0n1']})
        self.assertDictEqual(
                utils_disk.get_linux_disks(session, True), self.expected_disks)

    def test_create_partition_linux(self):
        session = FakeSession()
        self.assertEqual(utils_disk.create_partition_linux(
                session, 'sdb', '1G', '0M'), 'sdb1')
        self.expected_disks['sdb1'] = ['sdb1', '1G', 'partition',
                                       'drive_image2', '0x600508b1001ccccc']
        self.assertDictEqual(
                utils_disk.get_linux_disks(session, True), self.expected_disks)

    def test_configure_empty_linux_disk(self):
        session = FakeSession()
        self.assertEqual(utils_disk.configure_empty_linux_disk(
                session, 'sdb', '1G'), ['/mnt/sdb1'])
        self.expected_disks['sdb1'] = ['sdb1', '1G', 'partition',
                                       'drive_image2', '0x600508b1001ccccc']
        self.assertDictEqual(
                utils_disk.get_linux_disks(session, True), self.expected_disks)
        self.assertTrue(utils_disk.is_mount(
                '/dev/sdb1', '/mnt/sdb1', 'ext4', session=session))

    def test_delete_partition_linux(self):
        session = FakeSession()
        utils_disk.delete_partition_linux(session, 'sda2')
        del self.expected_disks['sda2']
        self.assertDictEqual(
                utils_disk.get_linux_disks(session, True), self.expected_disks)
        with unittest.mock.patch('virttest.utils_package.package_install',
                                 return_value=True):
            utils_disk.delete_partition_linux(session, 'sda1')
            del self.expected_disks['sda1']
            self.assertDictEqual(
                    utils_disk.get_linux_disks(session, True), self.expected_disks)

    def test_clean_partition_linux(self):
        session = FakeSession()
        utils_disk.clean_partition_linux(session, 'sdd')
        for i in range(1, 4):
            del self.expected_disks['sdd%s' % i]
        self.assertDictEqual(
                utils_disk.get_linux_disks(session, True), self.expected_disks)
        self.expected_disks['nvme0n1p1'] = ['nvme0n1p1', '80G', 'partition',
                                            'drive_image5', None]
        self.assertEqual(utils_disk.create_partition_linux(
                session, 'nvme0n1', '80G', '0M'), 'nvme0n1p1')
        self.assertDictEqual(
                utils_disk.get_linux_disks(session, True), self.expected_disks)
        utils_disk.clean_partition_linux(session, 'nvme0n1')
        del self.expected_disks['nvme0n1p1']
        self.assertDictEqual(
                utils_disk.get_linux_disks(session, True), self.expected_disks)

    def test_create_partition_windows(self):
        session = FakeSession()
        cmd = " echo create partition %s size=%s; echo list partition"
        with unittest.mock.patch('virttest.utils_disk._wrap_windows_cmd',
                                 return_value=wrap_windows_cmd(cmd)):
            self.assertEqual(utils_disk.create_partition_windows(
                    session, '1', '1G', '0M'), '1')


if __name__ == '__main__':
    unittest.main()
