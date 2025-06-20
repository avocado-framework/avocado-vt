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


#   Do not pause the domain during migration. The domain's memory will
#   be transferred to the destination host while the domain is running.
#   The migration may never converge if the domain is changing its memory
#   faster then it can be transferred. The domain can be manually paused
#   anytime during migration using virDomainSuspend.
#  
#   Since: 0.3.2
VIR_MIGRATE_LIVE = "VIR_MIGRATE_LIVE"

#   Tell the source libvirtd to connect directly to the destination host.
#   Without this flag the client (e.g., virsh) connects to both hosts and
#   controls the migration process. In peer-to-peer mode, the source
#   libvirtd controls the migration by calling the destination daemon
#   directly.
#  
#   Since: 0.7.2

VIR_MIGRATE_PEER2PEER = "VIR_MIGRATE_PEER2PEER"

# Tunnel migration data over libvirtd connection. Without this flag the
# source hypervisor sends migration data directly to the destination
# hypervisor. This flag can only be used when VIR_MIGRATE_PEER2PEER is
# set as well.
#
# Note the less-common spelling that we're stuck with:
# VIR_MIGRATE_TUNNELLED should be VIR_MIGRATE_TUNNELED.
#
# Since: 0.7.2
  
VIR_MIGRATE_TUNNELLED = "VIR_MIGRATE_TUNNELLED"

# Define the domain as persistent on the destination host after successful
# migration. If the domain was persistent on the source host and
# VIR_MIGRATE_UNDEFINE_SOURCE is not used, it will end up persistent on
# both hosts.
#
# Since: 0.7.3
  
VIR_MIGRATE_PERSIST_DEST = "VIR_MIGRATE_PERSIST_DEST"

# Undefine the domain on the source host once migration successfully
# finishes.
#
# Since: 0.7.3
  
VIR_MIGRATE_UNDEFINE_SOURCE = "VIR_MIGRATE_UNDEFINE_SOURCE"

# Leave the domain suspended on the destination host. virDomainResume (on
# the virDomainPtr returned by the migration API) has to be called
# explicitly to resume domain's virtual CPUs.
#
# Since: 0.7.5
  
VIR_MIGRATE_PAUSED = "VIR_MIGRATE_PAUSED"

# Migrate full disk images in addition to domain's memory. By default
# only non-shared non-readonly disk images are transferred. The
# VIR_MIGRATE_PARAM_MIGRATE_DISKS parameter can be used to specify which
# disks should be migrated.
#
# This flag and VIR_MIGRATE_NON_SHARED_INC are mutually exclusive.
#
# Since: 0.8.2
  
VIR_MIGRATE_NON_SHARED_DISK = "VIR_MIGRATE_NON_SHARED_DISK"

# Migrate disk images in addition to domain's memory. This is similar to
# VIR_MIGRATE_NON_SHARED_DISK, but only the top level of each disk's
# backing chain is copied. That is, the rest of the backing chain is
# expected to be present on the destination and to be exactly the same as
# on the source host.
#
# This flag and VIR_MIGRATE_NON_SHARED_DISK are mutually exclusive.
#
# Since: 0.8.2
  
VIR_MIGRATE_NON_SHARED_INC = "VIR_MIGRATE_NON_SHARED_INC"

# Protect against domain configuration changes during the migration
# process. This flag is used automatically when both sides support it.
# Explicitly setting this flag will cause migration to fail if either the
# source or the destination does not support it.
#
# Since: 0.9.4
  
VIR_MIGRATE_CHANGE_PROTECTION = "VIR_MIGRATE_CHANGE_PROTECTION"

# Force migration even if it is considered unsafe. In some cases libvirt
# may refuse to migrate the domain because doing so may lead to potential
# problems such as data corruption, and thus the migration is considered
# unsafe. For a QEMU domain this may happen if the domain uses disks
# without explicitly setting cache mode to "none". Migrating such domains
# is unsafe unless the disk images are stored on coherent clustered
# filesystem, such as GFS2 or GPFS.
#
# Since: 0.9.11
  
VIR_MIGRATE_UNSAFE = "VIR_MIGRATE_UNSAFE"

# Migrate a domain definition without starting the domain on the
# destination and without stopping it on the source host. Offline
# migration requires VIR_MIGRATE_PERSIST_DEST to be set.
#
# Offline migration may not copy disk storage or any other file based
# storage (such as UEFI variables).
#
# Since: 1.0.1
  
VIR_MIGRATE_OFFLINE = "VIR_MIGRATE_OFFLINE"

# Compress migration data. The compression methods can be specified using
# VIR_MIGRATE_PARAM_COMPRESSION. A hypervisor default method will be used
# if this parameter is omitted. Individual compression methods can be
# tuned via their specific VIR_MIGRATE_PARAM_COMPRESSION_ parameters.
#
# Since: 1.0.3
  
VIR_MIGRATE_COMPRESSED = "VIR_MIGRATE_COMPRESSED"

# Cancel migration if a soft error (such as I O error) happens during
# migration.
#
# Since: 1.1.0
  
VIR_MIGRATE_ABORT_ON_ERROR = "VIR_MIGRATE_ABORT_ON_ERROR"

# Enable algorithms that ensure a live migration will eventually converge.
# This usually means the domain will be slowed down to make sure it does
# not change its memory faster than a hypervisor can transfer the changed
# memory to the destination host. VIR_MIGRATE_PARAM_AUTO_CONVERGE_
# parameters can be used to tune the algorithm.
#
# Since: 1.2.3
  
VIR_MIGRATE_AUTO_CONVERGE = "VIR_MIGRATE_AUTO_CONVERGE"

# This flag can be used with RDMA migration (i.e., when
# VIR_MIGRATE_PARAM_URI starts with "rdma:  ") to tell the hypervisor
# to pin all domain's memory at once before migration starts rather then
# letting it pin memory pages as needed. This means that all memory pages
# belonging to the domain will be locked in host's memory and the host
# will not be allowed to swap them out.
#
# For QEMU KVM this requires hard_limit memory tuning element (in the
# domain XML) to be used and set to the maximum memory configured for the
# domain plus any memory consumed by the QEMU process itself. Beware of
# setting the memory limit too high (and thus allowing the domain to lock
# most of the host's memory). Doing so may be dangerous to both the
# domain and the host itself since the host's kernel may run out of
# memory.
#
# Since: 1.2.9

VIR_MIGRATE_RDMA_PIN_ALL = "VIR_MIGRATE_RDMA_PIN_ALL"

# Setting the VIR_MIGRATE_POSTCOPY flag tells libvirt to enable post-copy
# migration. However, the migration will start normally and
# virDomainMigrateStartPostCopy needs to be called to switch it into the
# post-copy mode. See virDomainMigrateStartPostCopy for more details.
#
# Since: 1.3.3
  
VIR_MIGRATE_POSTCOPY = "VIR_MIGRATE_POSTCOPY"

# Setting the VIR_MIGRATE_TLS flag will cause the migration to attempt
# to use the TLS environment configured by the hypervisor in order to
# perform the migration. If incorrectly configured on either source or
# destination, the migration will fail.
#
# Since: 3.2.0
  
VIR_MIGRATE_TLS = "VIR_MIGRATE_TLS"

# Send memory pages to the destination host through several network
# connections. See VIR_MIGRATE_PARAM_PARALLEL_ parameters for
# configuring the parallel migration.
#
# Since: 5.2.0
  
VIR_MIGRATE_PARALLEL = "VIR_MIGRATE_PARALLEL"

# Force the guest writes which happen when copying disk images for
# non-shared storage migration to be synchronously written to the
# destination. This ensures the storage migration converges for VMs
# doing heavy I O on fast local storage and slow mirror.
#
# Requires one of VIR_MIGRATE_NON_SHARED_DISK, VIR_MIGRATE_NON_SHARED_INC
# to be present as well.
#
# Since: 8.0.0
   
VIR_MIGRATE_NON_SHARED_SYNCHRONOUS_WRITES = "VIR_MIGRATE_NON_SHARED_SYNCHRONOUS_WRITES"

# Resume migration which failed in post-copy phase.
#
# Since: 8.5.0
  
VIR_MIGRATE_POSTCOPY_RESUME = "VIR_MIGRATE_POSTCOPY_RESUME"

# Use zero-copy mechanism for migrating memory pages. For QEMU KVM this
# means QEMU will be temporarily allowed to lock all guest pages in host's
# memory, although only those that are queued for transfer will be locked
# at the same time.
#
# Since: 8.5.0

VIR_MIGRATE_ZEROCOPY = "VIR_MIGRATE_ZEROCOPY"
