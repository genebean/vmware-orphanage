# vmware-orphanage

Find orphans on a VMware datastore and give them a home

The script is written in Python 3 and uses pyvmomi. It can be run directly or
via `docker run`. When running via Docker you can pass all arguments directly.
For example, you can execute `docker run --rm genebean/vmware-orphanage -h` to
see all available arguments.

# NOTE: Development is currently in process

The current version is not yet pushed to Docker Hub and does not yet register
the VM's it finds. It currently just reports on them.

## Usage

```
$ docker run --rm vmware-orphanage
usage: getorphanedvms.py [-h] -s HOST [-o PORT] -u USER -p PASSWORD
                         --datacenter DATACENTER --datastore DATASTORE
                         [--days DAYS]

Process args for retrieving all the Virtual Machines

optional arguments:
  -h, --help            show this help message and exit
  -s HOST, --host HOST  Remote host to connect to
  -o PORT, --port PORT  Port to connect on
  -u USER, --user USER  User name to use when connecting to host
  -p PASSWORD, --password PASSWORD
                        Password to use when connecting to host
  --datacenter DATACENTER
                        The datacenter to interact with
  --datastore DATASTORE
                        The datastore to search
  --days DAYS           VM's with activity in their log more recent than X
                        days will be ignored.
```