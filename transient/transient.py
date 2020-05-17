from . import qemu
from . import image
from . import ssh

import os
import pwd
import socket

from typing import cast, Optional, List, Dict, Any, Union


class TransientVm:
    store: image.ImageStore
    config: Dict[str, Any]
    vm_images: List[image.ImageInfo]
    ssh_port: Optional[int]

    def __init__(self, config: Dict[str, Any]) -> None:
        self.store = image.ImageStore()
        self.config = config
        self.vm_images = []
        self.ssh_port = None

    def __create_images(self, names: List[str]) -> List[image.ImageInfo]:
        return [self.store.create_vm_image(image_name, self.config["name"], idx)
                for idx, image_name in enumerate(names)]

    def __needs_ssh(self) -> bool:
        return (self.config["ssh_console"] is True or
                len(self.config["shared_folder"]) > 0)

    def __qemu_added_devices(self) -> List[str]:
        new_args = []
        for image in self.vm_images:
            new_args.extend(["-drive", "file={}".format(image.path())])

        if self.__needs_ssh():
            if self.config["ssh_console"] is True:
                new_args.append("-nographic")

            # Use userspace networking (so no root is needed), and bind
            # the random localhost port to guest port 22
            self.ssh_port = self.__allocate_random_port()
            new_args.extend(["-net", "nic,model=e1000",
                             "-net", "user,hostfwd=tcp::{}-:22".format(self.ssh_port)])
        return new_args

    def __allocate_random_port(self) -> int:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Binding to port 0 causes the kernel to allocate a port for us. Because
        # it won't reuse that port until is _has_ to, this can safely be used
        # as (for example) the ssh port for the guest and it 'should' be race-free
        s.bind(("", 0))
        addr = s.getsockname()
        s.close()
        return cast(int, addr[1])

    def __connect_ssh(self) -> int:
        assert(self.ssh_port is not None)

        client = ssh.SshClient(host="localhost",
                               port=self.ssh_port,
                               user=self.config["ssh_user"],
                               ssh_bin_name=self.config["ssh_bin_name"])
        return client.connect_wait(timeout=self.config["ssh_timeout"])

    def __current_user(self) -> str:
        return pwd.getpwuid(os.getuid()).pw_name

    def run(self) -> int:
        # First, download and setup any required disks
        self.vm_images = self.__create_images(self.config["image"])

        added_qemu_args = self.__qemu_added_devices()
        full_qemu_args = added_qemu_args + self.config["qemu_args"]

        runner = qemu.QemuRunner(full_qemu_args, quiet=self.config["ssh_console"])

        runner.start()

        for shared_spec in self.config["shared_folder"]:
            local, remote = shared_spec.split(":")
            ssh.do_sshfs_mount(timeout=self.config["ssh_timeout"],
                               local_dir=local, remote_dir=remote,
                               host="localhost",
                               ssh_bin_name=self.config["ssh_bin_name"],
                               remote_user=self.config["ssh_user"],
                               local_user=self.__current_user(),
                               port=self.ssh_port)

        if self.config["ssh_console"] is True:
            returncode = self.__connect_ssh()

            # Once the ssh connection closes, terminate the VM
            # TODO: signal handler to kill the VM even if `transient`
            # dies unexpectedly.
            runner.terminate()

            # If sigterm didn't work, kill it
            runner.kill()

            # Note that for ssh-console, we return the code of the ssh connection,
            # not the qemu process
            return returncode
        else:
            return runner.wait()
