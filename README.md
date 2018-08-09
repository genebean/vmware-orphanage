# vmware-orphanage

Find orphans on a VMware datastore and give them a home

The script is written in Python 3 and uses pyvmomi. It can be run directly or
via `docker run`. When running via Docker you can pass all arguments directly.
For example, you can execute `docker run --rm genebean/vmware-orphanage -h` to
see all available arguments.

# NOTE: Development is currently in process

The current version is not yet pushed to Docker Hub and does not yet register
the VM's it finds. It currently just reports on them.

