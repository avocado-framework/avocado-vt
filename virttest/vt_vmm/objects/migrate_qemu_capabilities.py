from enum import Enum, auto


# class MigrateCapabilities(Enum):
#     XBZRLE = auto()
#     AUTO_CONVERGE = auto()
#     RDMA_PIN_ALL = auto()
#     EVENTS = auto()
#     POSTCOPY = auto()
#     COMPRESS = auto()
#     PAUSE_BEFORE_SWITCHOVER = auto()
#     LATE_BLOCK_ACTIVATE = auto()
#     MULTIFD = auto()
#     BLOCK_DIRTY_BITMAPS = auto()
#     RETURN_PATH = auto()
#     ZERO_COPY_SEND = auto()
#     POSTCOPY_PREEMPT = auto()
#     SWITCHOVER_ACK = auto()

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



# QEMU_MIGRATION_CAPABILITIES = {
#     "XBZRLE": [
#         {
#             "name": "xbzrle",
#             "version": "(, qemu-x.y.z]",
#             "type": bool,
#         },
#         {
#             "name": "x-xbzrle",  # experimental feature
#             "version": "(qemu-x.y.z, )",
#             "type": bool,
#         },
#     ],
#     "AUTO_CONVERGE": [
#         {
#             "name": "auto-converge",
#             "version": "(, qemu-x.y.z]",
#             "type": bool,
#         },
#     ],
#     "RDMA_PIN_ALL": [
#         {
#             "name": "rdma-pin-all",
#             "version": "(, qemu-x.y.z]",
#             "type": bool,
#         }
#     ],
#     "EVENTS": [
#         {
#             "name": "events",
#             "version": "(, qemu-x.y.z]",
#             "type": bool,
#         },
#     ],
#     "POSTCOPY": [
#         {
#             "name": "postcopy-ram",
#             "version": "(, qemu-x.y.z]",
#             "type": bool,
#         },
#     ],
#     "COMPRESS": [
#         {
#             "name": "compress",
#             "version": "(, qemu-x.y.z]",
#             "type": bool,
#         },
#     ],
#     "PAUSE_BEFORE_SWITCHOVER": [
#         {
#             "name": "pause-before-switchover",
#             "version": "(, qemu-x.y.z)",
#             "type": bool,
#         },
#     ],
#     "LATE_BLOCK_ACTIVATE": [
#         {
#             "name": "late-block-activate",
#             "version": "(, qemu-x.y.z)",
#             "type": bool,
#         },
#     ],
#     "MULTIFD": [
#         {
#             "name": "multifd",
#             "version": "(, qemu-x.y.z]",
#             "type": bool,
#         },
#     ],
#     "BLOCK_DIRTY_BITMAPS": [
#         {
#             "name": "dirty-bitmaps",
#             "version": "(, qemu-x.y.z)",
#             "type": bool,
#         },
#     ],
#     "RETURN_PATH": [
#         {
#             "name": "return-path",
#             "version": "(, qemu-x.y.z)",
#             "type": bool,
#         },
#     ],
#     "ZERO_COPY_SEND": [
#         {
#             "name": "zero-copy-send",
#             "version": "(, qemu-x.y.z)",
#             "type": bool,
#         },
#     ],
#     "POSTCOPY_PREEMPT": [
#         {
#             "name": "postcopy-preempt",
#             "version": "(, qemu-x.y.z)",
#             "type": bool,
#         },
#     ],
#     "SWITCHOVER_ACK": [
#         {
#             "name": "switchover-ack",
#             "version": "(, qemu-x.y.z)",
#             "type": bool,
#         },
#     ],
# }
