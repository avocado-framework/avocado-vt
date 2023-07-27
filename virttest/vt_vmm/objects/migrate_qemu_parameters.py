from enum import Enum, auto


# class MigrateParameters(Enum):
#     COMPRESS_LEVEL,
#     COMPRESS_THREADS,
#     DECOMPRESS_THREADS,
#     THROTTLE_INITIAL,
#     THROTTLE_INCREMENT,
#     TLS_CREDS,
#     TLS_HOSTNAME,
#     MAX_BANDWIDTH,
#     DOWNTIME_LIMIT,
#     BLOCK_INCREMENTAL,
#     XBZRLE_CACHE_SIZE,
#     MAX_POSTCOPY_BANDWIDTH,
#     MULTIFD_CHANNELS,
#     MULTIFD_COMPRESSION,
#     MULTIFD_ZLIB_LEVEL,
#     MULTIFD_ZSTD_LEVEL,

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
    "MULTIFD_CHANNELS": "multi-fd-channels",
    "MULTIFD_COMPRESSION": "multifd-compression",
    "MULTIFD_ZLIB_LEVEL": "multifd-zlib-level",
    "MULTIFD_ZSTD_LEVEL": "multifd-zstd-level",
}

# QEMU_MIGRATION_PARAMETERS = {
#     "COMPRESS_LEVEL": [
#         {
#             "name": "compress-level",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#         {
#             "name": "x-compress-level",  # experimental feature
#             "version": "(qemu-x.y.z, )",
#             "type": str,
#         },
#     ],
#     "COMPRESS_THREADS": [
#         {
#             "name": "compress-threads",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "DECOMPRESS_THREADS": [
#         {
#             "name": "decompress-threads",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "THROTTLE_INITIAL": [
#         {
#             "name": "cpu-throttle-initial",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "THROTTLE_INCREMENT": [
#         {
#             "name": "cpu-throttle-increment",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "TLS_CREDS": [
#         {
#             "name": "tls-creds",
#             "version": "(, qemu-x.y.z]",
#             "type": str,
#         },
#     ],
#     "TLS_HOSTNAME": [
#         {
#             "name": "tls-hostname",
#             "version": "(, qemu-x.y.z]",
#             "type": str,
#         },
#     ],
#     "MAX_BANDWIDTH": [
#         {
#             "name": "max-bandwidth",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "DOWNTIME_LIMIT": [
#         {
#             "name": "downtime-limit",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "BLOCK_INCREMENTAL": [
#         {
#             "name": "block-incremental",
#             "version": "(, qemu-x.y.z]",
#             "type": bool,
#         },
#     ],
#     "XBZRLE_CACHE_SIZE": [
#         {
#             "name": "xbzrle-cache-size",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "MAX_POSTCOPY_BANDWIDTH": [
#         {
#             "name": "max-postcopy-bandwidth",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "MULTIFD_CHANNELS": [
#         {
#             "name": "multi-fd-channels",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "MULTIFD_COMPRESSION": [
#         {
#             "name": "multifd-compression",
#             "version": "(, qemu-x.y.z]",
#             "type": str,
#         },
#     ],
#     "MULTIFD_ZLIB_LEVEL": [
#         {
#             "name": "multifd-zlib-level",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
#     "MULTIFD_ZSTD_LEVEL": [
#         {
#             "name": "multifd-zstd-level",
#             "version": "(, qemu-x.y.z]",
#             "type": int,
#         },
#     ],
# }


# def parse_qemu_migration_parameter(qemu_parameter, value):
#     # Parse the qemu migration capability to the virt migration capability
#     for parameter, qemu_parameters in QEMU_MIGRATION_PARAMETERS.items():
#         for _parameter in qemu_parameters:
#             if _parameter["name"] == qemu_parameter:
#                 return parameter, value
#     else:
#         raise ValueError(f"Unsupported type for qemu parameter {qemu_parameter}")
#
#
# def parse_virt_migration_parameter(virt_parameter, value):
#     # Parse the virt migration capability to the qemu migration capability
#     for _parameter, qemu_parameters in QEMU_MIGRATION_PARAMETERS.items():
#         if virt_parameter == _parameter:
#             return qemu_parameters, value
#     else:
#         raise ValueError(f"Unsupported type for virt migration parameter {virt_parameter}")
