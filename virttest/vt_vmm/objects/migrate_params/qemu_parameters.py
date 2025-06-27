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


QEMU_MIGRATION_PARAMETERS = {
    "COMPRESS_LEVEL": "compress-level",
    "COMPRESS_THREADS": "compress-threads",
    "DECOMPRESS_THREADS": "decompress-threads",
    "THROTTLE_INITIAL": "cpu-throttle-initial",
    "THROTTLE_INCREMENT": "cpu-throttle-increment",
    "TLS_CREDS": "tls-creds",
    "TLS_HOSTNAME": "tls-hostname",
    "MAX_BANDWIDTH": "max-bandwidth",
    "DOWNTIME_LIMIT": "downtime-limit",
    "BLOCK_INCREMENTAL": "block-incremental",
    "XBZRLE_CACHE_SIZE": "xbzrle-cache-size",
    "MAX_POSTCOPY_BANDWIDTH": "max-postcopy-bandwidth",
    "MULTIFD_CHANNELS": "multifd-channels",
    "MULTIFD_COMPRESSION": "multifd-compression",
    "MULTIFD_ZLIB_LEVEL": "multifd-zlib-level",
    "MULTIFD_ZSTD_LEVEL": "multifd-zstd-level",
}
