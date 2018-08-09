#!/usr/bin/env python
"""
This module demonstrates how to find virtual machines that
exist on a datastore, but are not part of the inventory.
This can be useful to find orphaned virtual machines that
are still taking up datastore space, but not currently
being used.

Issues:
    Currently works with Windows based vCenter servers only.
    Still working on vCenter Server Appliance

Example:

      $./getorphanedvms.py -s 10.90.2.10 -u vcenter.svc -p password
"""

from pyVim.connect import SmartConnect
from pyVim.connect import Disconnect
from pyVmomi import vmodl
from pyVmomi import vim
import argparse
import atexit
from datetime import datetime
from datetime import timedelta
import pprint
import requests
from urllib.parse import urljoin
from urllib.parse import urlsplit

VMX_PATH = []
DS_VM = {}
INV_VM = []

# dates used for comparisons
TODAY = datetime.now()
DATE_IN_PAST = None


def get_args():
    """
    Supports the command-line arguments listed below.
    function to parse through args for connecting to ESXi host or
    vCenter server function taken from getallvms.py script
    from pyvmomi github repo
    """
    parser = argparse.ArgumentParser(
        description='Process args for retrieving all the Virtual Machines')
    parser.add_argument(
        '-s', '--host', required=True, action='store',
        help='Remote host to connect to')
    parser.add_argument(
        '-o', '--port', type=int, default=443, action='store',
        help='Port to connect on')
    parser.add_argument(
        '-u', '--user', required=True, action='store',
        help='User name to use when connecting to host')
    parser.add_argument(
        '-p', '--password', required=True, action='store',
        help='Password to use when connecting to host')
    parser.add_argument(
        '--datacenter', required=True, action='store',
        help='The datacenter to interact with')
    parser.add_argument(
        '--datastore', required=True, action='store',
        help='The datastore to search')
    parser.add_argument(
        '--days', type=int, default=2, action='store',
        help="VM's with activity in their log more recent than X days will be ignored."
    )
    args = parser.parse_args()
    return args


def find_vmx(dsbrowser, dsname, datacenter, fulldsname):
    """
    function to search for VMX files on any datastore that is passed to it
    """
    args = get_args()
    search = vim.HostDatastoreBrowserSearchSpec()
    search.matchPattern = "*.vmx"
    search_ds = dsbrowser.SearchDatastoreSubFolders_Task(dsname, search)
    while search_ds.info.state != "success":
        pass
    # results = search_ds.info.result
    # print(results)

    for search_result in search_ds.info.result:
        dsfolder = search_result.folderPath
        for found_file in search_result.file:
            try:
                dsfile = found_file.path
                vmfold = dsfolder.split("]")
                vmfold = vmfold[1]
                vmfold = vmfold[1:]
                vmxurl = "https://%s/folder/%s%s?dcPath=%s&dsName=%s" % \
                         (args.host, vmfold, dsfile, datacenter, fulldsname)
                VMX_PATH.append(vmxurl)
                # print(vmxurl)
            except Exception as e:
                print("Caught exception : " + str(e))
                return -1

def examine_vmx(dsname):
    """
    function to download any vmx file passed to it via the datastore browser
    and find the 'vc.uuid' and 'displayName'
    """
    args = get_args()
    try:
        for file_vmx in VMX_PATH:
            # print(file_vmx)

            username = args.user
            password = args.password
            log_url = urljoin(file_vmx, 'vmware.log') + '?' + urlsplit(file_vmx).query
            r = requests.get(log_url, auth=(username, password))
            if r.status_code == requests.codes.ok:
                logfile = r.text.splitlines()
                last_line = logfile[-1]
                log_timestamp = datetime.strptime(last_line.split('|')[0].replace('Z', 'UTC'), "%Y-%m-%dT%H:%M:%S.%f%Z")

                if log_timestamp < DATE_IN_PAST:
                    # print(log_timestamp.isoformat() + " is before " + DATE_IN_PAST.isoformat())

                    vmxfile = requests.get(file_vmx, auth=(username, password)).text.splitlines()
                    for line in vmxfile:
                        if line.startswith("displayName"):
                            dn = line
                        elif line.startswith("vc.uuid"):
                            vcid = line
                        # print(line)

                    uuid = vcid.replace('"', "")
                    uuid = uuid.replace("vc.uuid = ", "")
                    uuid = uuid.strip("\n")
                    uuid = uuid.replace(" ", "")
                    uuid = uuid.replace("-", "")
                    newdn = dn.replace('"', "")
                    newdn = newdn.replace("displayName = ", "")
                    newdn = newdn.strip("\n")
                    vmfold = file_vmx.split("folder/")
                    vmfold = vmfold[1].split("/")
                    vmfold = vmfold[0]
                    dspath = "%s/%s" % (dsname, vmfold)
                    tempds_vm = [newdn, dspath]
                    DS_VM[uuid] = tempds_vm
                    
                    # print(newdn + "'s last log entry was " + log_timestamp.isoformat())                    

    except Exception as e:
        print("Caught exception in examine_vmx function : " + str(e))

def getvm_info(vm, depth=1):
    """
    Print information for a particular virtual machine or recurse
    into a folder with depth protection
    from the getallvms.py script from pyvmomi from github repo
    """
    maxdepth = 10

    # if this is a group it will have children. if it does,
    # recurse into them and then return

    if hasattr(vm, 'childEntity'):
        if depth > maxdepth:
            return
        vmlist = vm.childEntity
        for c in vmlist:
            getvm_info(c, depth+1)
        return
    if hasattr(vm, 'CloneVApp_Task'):
        vmlist = vm.vm
        for c in vmlist:
            getvm_info(c)
        return

    try:
        uuid = vm.config.instanceUuid
        uuid = uuid.replace("-", "")
        INV_VM.append(uuid)
    except Exception as e:
        print("Caught exception : " + str(e))
        return -1

def find_match(uuid):
    """
    function takes vc.uuid from the vmx file and the instance uuid from
    the inventory VM and looks for match if no match is found
    it is printed out.
    """
    a = 0
    for temp in INV_VM:
        if uuid == temp:
            a = a+1
    if a < 1:
        print(DS_VM[uuid])

def update_date_in_past(number_of_days):
    """
    function to update teh DATE_IN_PAST global variable
    """
    global DATE_IN_PAST
    DATE_IN_PAST = TODAY - timedelta(days=number_of_days)

def updatevmx_path():
    """
    function to set the VMX_PATH global variable to null
    """
    global VMX_PATH
    VMX_PATH = []

def main():
    """
    function runs all of the other functions. Some parts of this function
    are taken from the getallvms.py script from the pyvmomi gihub repo
    """
    args = get_args()
    update_date_in_past(args.days)
    try:
        si = None
        try:
            si = SmartConnect(host=args.host,
                              user=args.user,
                              pwd=args.password,
                              port=int(args.port))
        except IOError as e:
            pass

        if not si:
            print("Could not connect to the specified host using " \
                  "specified username and password")
            return -1

        atexit.register(Disconnect, si)

        content = si.RetrieveContent()

        datacenters = content.rootFolder.childEntity
        target_datacenter = None
        for dc in datacenters:
            if dc.name == args.datacenter:
                target_datacenter = dc
                break
        if target_datacenter == None:
            print("Couldn't find a datacenter named '%s'" % args.datacenter)
            return -1

        datastores = target_datacenter.datastore
        target_datastore = None
        for ds in datastores:
            if ds.summary.name == args.datastore:
                target_datastore = ds
                break
        if target_datastore == None:
            print("Couldn't find a datastore named '%s'" % args.datastore)
            return -1

        vmfolder = target_datacenter.vmFolder
        vmlist = vmfolder.childEntity
        dsvmkey = []

        
        find_vmx(target_datastore.browser, "[%s]" % target_datastore.summary.name, target_datacenter.name,
                    target_datastore.summary.name)
        examine_vmx(target_datastore.summary.name)
        updatevmx_path()

        # each VM found in the inventory is passed to the getvm_info
        # function to get it's instanceuuid

        for vm in vmlist:
            getvm_info(vm)
        
        # each uuid in the dsvmkey list is passed to the find_match
        # function to look for a match

        print("The following virtual machine(s) do not exist in the " \
              "inventory, but exist on a datastore " \
              "(Display Name, Datastore/Folder name):")
        for match in dsvmkey:
            find_match(match)

        Disconnect(si)
    except vmodl.MethodFault as e:
        print("Caught vmodl fault : " + e.msg)
        return -1
    except Exception as e:
        print("Caught exception : " + str(e))
        return -1

    return 0

# Start program
if __name__ == "__main__":
    main()
