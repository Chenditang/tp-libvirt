import logging
import xml.dom.minidom
from virttest import aexpect
from virttest import remote
from virttest import virsh
from autotest.client.shared import error
from virttest.utils_test import libvirt as utlv
from virttest.utils_libvirtd import Libvirtd
from virttest.libvirt_xml import vm_xml


def run(test, params, env):
    """
    Test the command virsh metadata

    Run in 4 steps:
    1. Set domain metadata
    2. Get domain metadata
    3. Restart libvirtd then get domain metadata again
    4. Remove domain metadata then get domain metadata again
    """
    vm_name = params.get("main_vm")
    vm = env.get_vm(vm_name)
    metadata_uri = params.get("metadata_uri")
    metadata_key = params.get("metadata_key")
    metadata_value = params.get("metadata_value", "")
    metadata_option = params.get("metadata_option", "")
    virsh_dargs = {'debug': True, 'ignore_status': True}
    metadata_set = "yes" == params.get("metadata_set", "no")
    metadata_get = "yes" == params.get("metadata_get", "yes")
    metadata_remove = "yes" == params.get("metadata_remove", "no")
    restart_libvirtd = "yes" == params.get("restart_libvirtd", "no")
    status_error = "yes" == params.get("status_error", "no")
    if not metadata_uri:
        raise error.TestErrorr("'uri' is needed")
    vmxml = vm_xml.VMXML.new_from_dumpxml(vm_name)
    # Start VM
    if vm.state() != "running":
        vm.destroy()
        vm.start()

    def pretty_xml(xml_str):
        return xml.dom.minidom.parseString(xml_str).toprettyxml()

    def check_result(result, expect_status, expect_output=None):
        """
        Check virsh metadata command
        """
        utlv.check_exit_status(result, expect_status)
        if result.exit_status == 0 and expect_output:
            expect_output = pretty_xml(expect_output)
            logging.debug("Expect metadata: %s", expect_output)
            output = result.stdout.strip()
            output = pretty_xml(output)
            logging.debug("Command get metadata: %s", output)
            if output != expect_output:
                raise error.TestFail("Metadat is not expected")

    def get_metadata():
        """
        Get domain metadata
        """
        option = metadata_option.replace("--edit", "")
        result = virsh.metadata(vm_name,
                                metadata_uri,
                                options=option,
                                key=metadata_key,
                                **virsh_dargs)
        return result

    try:
        # Set metadata XML
        if metadata_set:
            if not metadata_key:
                raise error.TestErrorr("'key' is needed")
            if not metadata_value:
                raise error.TestErrorr("New metadata is needed")
            # Parse metadata value
            if "--edit" in metadata_option:
                virsh_cmd = r"virsh metadata %s --uri %s --key %s %s"
                virsh_cmd = virsh_cmd % (vm_name, metadata_uri,
                                         metadata_key, metadata_option)
                session = aexpect.ShellSession("sudo -s")
                logging.info("Running command: %s", virsh_cmd)
                try:
                    session.sendline(virsh_cmd)
                    session.sendline(r":insert")
                    session.sendline(metadata_value)
                    session.sendline(".")
                    session.send('ZZ')
                    remote.handle_prompts(session, None, None, r"[\#\$]\s*$",
                                          debug=True)
                except Exception, e:
                    logging.error("Error occured: %s", e)
                session.close()
            else:
                result = virsh.metadata(vm_name,
                                        metadata_uri,
                                        options=metadata_option,
                                        key=metadata_key,
                                        new_metadata=metadata_value,
                                        **virsh_dargs)
                check_result(result, status_error)
            if "--config" in metadata_option:
                vm.destroy()
                vm.start()
                check_result(get_metadata(), status_error, metadata_value)
        # Get metadata
        if metadata_get:
            check_result(get_metadata(), status_error, metadata_value)

        # Restart libvirtd:
        if restart_libvirtd:
            libvirtd = Libvirtd()
            libvirtd.restart()
            # Get metadata again
            check_result(get_metadata(), status_error, metadata_value)
        # Remove metadata
        if metadata_remove:
            remove_option = metadata_option.replace("--edit", "")
            remove_option += " --remove"
            result = virsh.metadata(vm_name,
                                    metadata_uri,
                                    options=remove_option,
                                    key=metadata_key,
                                    **virsh_dargs)
            check_result(result, status_error)
            # Get metadata again
            check_result(get_metadata(), True)
    finally:
        vmxml.sync()
