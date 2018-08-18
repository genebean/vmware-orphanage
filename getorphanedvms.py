#!/usr/bin/env python3
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


import argparse
import atexit
from lib.tracing import init_tracer
from opentracing_instrumentation.request_context import get_current_span, span_in_context
import pprint
from pyVim.connect import Disconnect
from pyVim.connect import SmartConnect
from pyVmomi import vmodl
from pyVmomi import vim
import requests
import time
from urllib.parse import urljoin
from urllib.parse import urlsplit

TRACER = None
VMX_PATH = []
DS_VM = {}
INV_VM = []
UNREGISTERED_VMS = []

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
    args = parser.parse_args()
    return args

def find_vmx(dsbrowser, dsname, datacenter, fulldsname):
    """
    function to search for VMX files on any datastore that is passed to it
    """
    with TRACER.start_span('find-vmx') as span:
        span.set_tag('datacenter', datacenter)
        span.set_tag('datastore-name', fulldsname)
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

def get_and_parse_vmx_file(dsname, vmx_file, username, password):
    """
    function to download any vmx file passed to it via the datastore browser
    and find the 'vc.uuid' and 'displayName'
    """
    root_span = get_current_span()
    with TRACER.start_span('get-and-parse-vmx-file', child_of=root_span) as span:
        try:
            r = requests.get(vmx_file, auth=(username, password))
            if r.status_code == requests.codes.ok:
                span.log_kv({'event': 'downloaded-vmx-file', 'value': vmx_file})
                vmxfile = r.text.splitlines()
                vcid = None
                for line in vmxfile:
                    # print(line)
                    if line.startswith("displayName"):
                        dn = line
                        newdn = dn.replace('"', "")
                        newdn = newdn.replace("displayName = ", "")
                        newdn = newdn.strip("\n")
                    elif line.startswith("vc.uuid"):
                        vcid = line
                if vcid is None:
                    uuid = 'not-found'
                    print('No uuid found for ' + newdn)
                else:
                    uuid = vcid.replace('"', "")
                    uuid = uuid.replace("vc.uuid = ", "")
                    uuid = uuid.strip("\n")
                    uuid = uuid.replace(" ", "")
                    uuid = uuid.replace("-", "")

                vmfold = vmx_file.split("folder/")
                vmfold = vmfold[1].split("/")
                vmfold = vmfold[0]
                dspath = "%s/%s" % (dsname, vmfold)
                tempds_vm = [newdn, dspath]
                DS_VM[uuid] = tempds_vm
                span.set_tag('vm-uuid', uuid)
                span.set_tag('vm-dn', newdn)

                # print(newdn + "'s last log entry was " + log_timestamp.isoformat())
            else:
                span.log_kv({'event': 'failed-downloaded-of-vmx-file', 'value': vmx_file})
        except Exception as e:
            print("Caught exception in get_and_parse_vmx_file function : " + str(e))
            print("The file is from " + vmx_file)
            r = requests.get(vmx_file, auth=(username, password))
            vmxfile_text = r.text.splitlines()
            print(vmxfile_text)

def examine_vmx(dsname):
    """
    function to loop over vmx files passed to it via the datastore browser
    """
    with TRACER.start_span('examine-vmx') as span:
        span.set_tag('datastore-name', dsname)
        args = get_args()
        try:
            for file_vmx in VMX_PATH:
                # print(file_vmx)
                username = args.user
                password = args.password
                with span_in_context(span):
                    get_and_parse_vmx_file(dsname, file_vmx, username, password)                  

        except Exception as e:
            print("Caught exception in examine_vmx function : " + str(e))

def getvm_info(vm, depth=1):
    """
    Print information for a particular virtual machine or recurse
    into a folder with depth protection
    from the getallvms.py script from pyvmomi from github repo
    """
    root_span = get_current_span()
    with TRACER.start_span('getvm-info', child_of=root_span) as span:
        maxdepth = 10

        # if this is a group it will have children. if it does,
        # recurse into them and then return

        if hasattr(vm, 'childEntity'):
            if depth > maxdepth:
                return
            vmlist = vm.childEntity
            for c in vmlist:
                with span_in_context(span):
                    getvm_info(c, depth+1)
            return
        if hasattr(vm, 'CloneVApp_Task'):
            vmlist = vm.vm
            for c in vmlist:
                with span_in_context(span):
                    getvm_info(c)
            return

        try:
            uuid = vm.config.instanceUuid
            uuid = uuid.replace("-", "")
            INV_VM.append(uuid)
            span.set_tag('vm-uuid', uuid)
        except Exception as e:
            print("Caught exception : " + str(e))
            return -1

def find_match(uuid):
    """
    function takes vc.uuid from the vmx file and the instance uuid from
    the inventory VM and looks for match if no match is found
    it is added to the UNREGISTERD_VMS list.
    """
    root_span = get_current_span()
    with TRACER.start_span('find-match', child_of=root_span) as span:
        span.set_tag('vm-uuid', uuid)
        a = 0
        for temp in INV_VM:
            if uuid == temp:
                a = a+1
        if a < 1:
            UNREGISTERED_VMS.append(DS_VM[uuid])
            # print(DS_VM[uuid])

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
    global TRACER
    TRACER = init_tracer('vmware-orphanage')
    args = get_args()
    try:
        with TRACER.start_span('connect-to-vcenter') as span:
            si = None
            try:
                si = SmartConnect(host=args.host,
                                user=args.user,
                                pwd=args.password,
                                port=int(args.port))
            except IOError as e:
                print("Caught exception : " + str(e))
                return -1

            if si:
                span.log_kv({'event': 'connected-to-vcenter', 'value': args.host})
                atexit.register(Disconnect, si)
            else:
                print("Could not connect to the specified host using " \
                    "specified username and password")
                return -1

        with TRACER.start_span('get-info-from-vcenter') as span:
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

        
        find_vmx(target_datastore.browser,
                 "[%s]" % target_datastore.summary.name,
                 target_datacenter.name,
                 target_datastore.summary.name)

        vmx_count = len(VMX_PATH)
        examine_vmx(target_datastore.summary.name)
        updatevmx_path()

        # each VM found in the inventory is passed to the getvm_info
        # function to get it's instanceuuid

        with TRACER.start_span('get-vm-uuids') as span:
            with span_in_context(span):
                for vm in vmlist:
                    getvm_info(vm)
        
        # each key from the DS_VM hashtable is added to a separate
        # list for comparison later

        for a in DS_VM.keys():
            dsvmkey.append(a)

        # each uuid in the dsvmkey list is passed to the find_match
        # function to look for a match
        with TRACER.start_span('find-unregistered-vms') as span:
            with span_in_context(span):
                for uuid in dsvmkey:
                    find_match(uuid)

        print("The following virtual machine(s) do not exist in the " \
              "inventory, but exist on a datastore " \
              "(Display Name, Datastore/Folder name):")
        print("")
        for orphan in UNREGISTERED_VMS:
            print(orphan)
        
        print("")
        print("VMX files found: " + str(vmx_count))
        print("VM's in inventory: " + str(len(INV_VM)))
        print("Orphans found: " + str(len(UNREGISTERED_VMS)))

        Disconnect(si)

        # yield to IOLoop to flush the spans
        time.sleep(2)
    except vmodl.MethodFault as e:
        print("Caught vmodl fault : " + e.msg)
        return -1
    except Exception as e:
        print("Caught exception : " + str(e))
        return -1

    # yield to IOLoop to flush the spans
    time.sleep(2)
    TRACER.close()

    return 0

# Start program
if __name__ == "__main__":
    main()
