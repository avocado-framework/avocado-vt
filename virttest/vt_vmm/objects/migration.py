class MigrationConfig(object):
    MIGRATION_PROTOS = ()


class QemuMigrationConfig(MigrationConfig):
    MIGRATION_PROTOS = ("rdma", "x-rdma", "tcp", "unix", "exec", "fd")


class LibvirtMigrationConfig(MigrationConfig):
    MIGRATION_PROTOS = ("rdma", "x-rdma", "tcp", "unix", "exec", "fd")
