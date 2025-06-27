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
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>


QEMU_MIGRATION_CAPABILITIES = {
    "XBZRLE": "xbzrle",
    "AUTO_CONVERGE": "auto-converge",
    "RDMA_PIN_ALL": "rdma-pin-all",
    "EVENTS": "events",
    "POSTCOPY": "postcopy-ram",
    "COMPRESS": "compress",
    "PAUSE_BEFORE_SWITCHOVER": "pause-before-switchover",
    "LATE_BLOCK_ACTIVATE": "late-block-activate",
    "MULTIFD": "multifd",
    "BLOCK_DIRTY_BITMAPS": "dirty-bitmaps",
    "RETURN_PATH": "return-path",
    "ZERO_COPY_SEND": "zero-copy-send",
    "POSTCOPY_PREEMPT": "postcopy-preempt",
    "SWITCHOVER_ACK": "switchover-ack",
}
