from __future__ import print_function

import os.path
import tarfile
import tempfile
import time

from sic_framework.core import utils
from sic_framework.core.connector import SICConnector
from sic_framework.core import sic_logging
from sic_framework.core.sic_redis import SICRedis

class SICLibrary(object):
    """
    A library to be installed on a remote device.
    """

    def __init__(self, name, lib_path="", download_cmd="", version=None, lib_install_cmd=""):
        self.name = name
        self.lib_path = lib_path
        self.download_cmd = download_cmd
        self.version = version
        self.lib_install_cmd = lib_install_cmd
        self.logger = sic_logging.get_sic_logger(name="SICLibraryInstaller")

    def check_if_installed(self, pip_freeze):
        """
        Check to see if a python library name + version is in the 'pip freeze' output of a remote device.
        """
        for lib in pip_freeze:
            lib = lib.replace('\n','')
            lib_name, lib_ver = lib.split('==')
            if self.name == lib_name:
                self.logger.debug("Found package: {}".format(lib))
                # check to make sure version matches 
                if self.version:
                    if self.version in lib_ver:
                        return True
                    else:
                        return False
                return True
        return False
    
    def install(self, ssh):
        """
        Download and install this Python library on a remote device
        """
        self.logger.info("Installing {} on remote device ".format(self.name))

        # download the binary first if necessary, as is the case with Pepper
        if self.download_cmd:
            stdin, stdout, stderr = ssh.exec_command(
                """cd {} && {} && echo "EXIT STATUS: $?" """.format(self.lib_path, self.download_cmd)
            )

            output = "".join(stdout.readlines())
            if "EXIT STATUS: 0" not in output:
                err = "".join(stderr.readlines())
                self.logger.error("Command: cd {} && {} \n Gave error:".format(self.lib_path, self.download_cmd))
                self.logger.error(err)
                raise RuntimeError(
                    "Error while downloading library on remote device."
                )


        # install the library
        stdin, stdout, stderr = ssh.exec_command(
            "cd {} && {}".format(self.lib_path, self.lib_install_cmd)
        )

        output = "".join(stdout.readlines())
        if "Successfully installed" not in output:
            err = "".join(stderr.readlines())
            self.logger.error("Command: cd {} && {} \n Gave error:".format(self.lib_path, self.lib_install_cmd))
            self.logger.error(err)
            raise RuntimeError(
                "Error while installing library on remote device. Please consult manual installation instructions."
            )
        else:
            self.logger.info("Successfully installed {} package".format(self.name))


def exclude_pyc(tarinfo):
    if tarinfo.name.endswith(".pyc"):
        return None
    else:
        return tarinfo


class SICDevice(object):
    """
    Abstract class to facilitate property initialization for SICConnector properties.
    This way components of a device can easily be used without initializing all device components manually.
    """

    def __new__(cls, *args, **kwargs):
        """ Choose specific imports dependend on the type of device.

        Reasoning: Alphamini does not support these imports; they are only needed for remotely installing packages on robots from the local machine
        """
        instance = super(SICDevice, cls).__new__(cls)

        if cls.__name__ in ("Nao", "Pepper", "Alphamini"):
            import six
            if six.PY3:
                global pathlib, paramiko, SCPClient
                import pathlib
                import paramiko
                from scp import SCPClient

        return instance

    def __init__(self, ip, username=None, passwords=None, port=22):
        """
        Connect to the device and ensure an up to date version of the framework is installed
        :param ip: the ip adress of the device
        :param username: the ssh login name
        :param passwords: the (list) of passwords to use
        """
        self.connectors = dict()
        self.configs = dict()
        self.ip = ip
        self.port = port

        self._redis = SICRedis()
        self._PING_TIMEOUT = 3

        self.logger = sic_logging.get_sic_logger(name="{}DeviceManager".format(self.__class__.__name__))
        sic_logging.SIC_LOG_SUBSCRIBER.subscribe_to_log_channel()
        
        self.logger.info("Initializing device with ip: {ip}".format(ip=ip))

        if username is not None:

            if not isinstance(passwords, list):
                passwords = [passwords]

            if not utils.ping_server(self.ip, port=self.port, timeout=3):
                raise RuntimeError(
                    "Could not connect to device on ip {}. Please check if it is reachable.".format(
                        self.ip
                    )
                )

            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # allow_agent=False, look_for_keys=False to disable asking for keyring (just use the password)
            for p in passwords:
                try:
                    self.ssh.connect(
                        self.ip,
                        port=self.port,
                        username=username,
                        password=p,
                        timeout=3,
                        allow_agent=False,
                        look_for_keys=False,
                    )
                    break
                except (
                    paramiko.ssh_exception.AuthenticationException,
                    paramiko.ssh_exception.BadAuthenticationType,
                ):
                    pass
            else:
                raise paramiko.ssh_exception.AuthenticationException(
                    "Could not authenticate to device, please check ip adress and/or credentials. (Username: {} Passwords: {})".format(
                        username, passwords
                    )
                )

    def get_last_modified(self, root, paths):
        last_modified = 0

        for file_or_folder in paths:
            file_or_folder = root + file_or_folder
            if os.path.isdir(file_or_folder):
                sub_last_modified = max(
                    os.path.getmtime(root) for root, _, _ in os.walk(file_or_folder)
                )
                last_modified = max(sub_last_modified, last_modified)
            elif os.path.isfile(file_or_folder):
                last_modified = max(os.path.getmtime(file_or_folder), last_modified)

        assert last_modified > 0, "Could not find any files to transfer."
        last_modified = time.ctime(last_modified).replace(" ", "_").replace(":", "-")
        return last_modified

    def auto_install(self):
        """
        Install the SICFramework on the device.
        :return:
        """
        # Find framework root folder
        root = str(pathlib.Path(__file__).parent.parent.parent.resolve())
        # assert os.path.basename(root) == "framework", "Could not find SIC 'framework' directory."

        # List of selected files and directories to be zipped and transferred
        selected_files = [
            "/setup.py",
            "/conf",
            "/lib",
            "/sic_framework/core",
            "/sic_framework/devices",
            "/sic_framework/__init__.py",
        ]

        last_modified = self.get_last_modified(root, selected_files)

        # Create a signature for the framework
        framework_signature = "~/framework/sic_version_signature_{}_{}".format(
            utils.get_ip_adress(), last_modified
        )

        # Check if the framework signature file exists
        stdin, stdout, stderr = self.ssh.exec_command(
            "ls {}".format(framework_signature)
        )
        file_exists = len(stdout.readlines()) > 0

        if file_exists:
            self.logger.info("Up to date framework is installed on the remote device.")
            return

        # prefetch slow pip freeze command
        _, stdout_pip_freeze, _ = self.ssh.exec_command("pip freeze")

        def progress(filename, size, sent):
            self.logger.info(
                "\r {} progress: {}".format(
                    filename.decode("utf-8"), round(float(sent) / float(size) * 100, 2)
                ),
                end="",
            )

        self.logger.info("Copying framework to the remote device.")
        with SCPClient(self.ssh.get_transport(), progress=progress) as scp:

            # Copy the framework to the remote computer
            with tempfile.NamedTemporaryFile(
                suffix="_sic_files.tar.gz", delete=False
            ) as f:
                with tarfile.open(fileobj=f, mode="w:gz") as tar:
                    for file in selected_files:
                        tar.add(root + file, arcname=file, filter=exclude_pyc)

                f.flush()
                self.ssh.exec_command("mkdir ~/framework")
                scp.put(f.name, remote_path="~/framework/sic_files.tar.gz")
                self.logger.info()  # newline after progress bar
            # delete=False for windows compatibility, must delete file manually
            os.unlink(f.name)

            # Unzip the file on the remote server
            # use --touch to prevent files from having timestamps of 1970 which intefere with python caching
            stdin, stdout, stderr = self.ssh.exec_command(
                "cd framework && tar --touch -xvf sic_files.tar.gz"
            )

            err = stderr.readlines()
            if len(err) > 0:
                self.logger.error("".join(err))
                raise RuntimeError(
                    "\n\nError while extracting library on remote device. Please consult manual installation instructions."
                )

            # Remove the zipped file
            self.ssh.exec_command("rm ~/framework/sic_files.tar.gz")

        # Check and/or install the framework and libraries on the remote computer
        self.logger.info("Checking if libraries are installed on the remote device.")
        # stdout_pip_freeze is prefetched above because it is slow
        # remote_libs = stdout_pip_freeze.readlines()
        # for lib in _LIBS_TO_INSTALL:
        #     if not lib.check_if_installed(remote_libs):
        #         lib.install(self.ssh)

        # Remove signatures from the remote computer
        # add own signature to the remote computer
        self.ssh.exec_command("rm ~/framework/sic_version_signature_*")
        self.ssh.exec_command("touch {}".format(framework_signature))

    def ssh_command(self, command):
        """
        Executes the given command and logs any exceptions that may occur

        :param command: command to run on ssh client
        :type command: string
        """
        try:
            return self.ssh.exec_command(command)
        except paramiko.AuthenticationException as e:
            self.logger.error(
                "Encountered AuthenticationException when trying to execute ssh command: {}".format(
                    e
                )
            )
        except paramiko.BadHostKeyException:
            self.logger.error(
                "Encountered BadHostKeyException when trying to execute ssh command: {}".format(
                    e
                )
            )
        except Exception as e:
            self.logger.error(
                "Encountered unknown exception while trying to execute ssh command: {}".format(
                    e
                )
            )

    def _get_connector(self, component_connector):
        """
        Get the active connection the component, or initialize it if it is not yet connected to.

        :param component_connector: The component connector class to start, e.g. NaoCamera
        :return: SICConnector
        """

        assert issubclass(
            component_connector, SICConnector
        ), "Component connector must be a SICConnector"

        if component_connector not in self.connectors:
            conf = self.configs.get(component_connector, None)

            try:
                self.connectors[component_connector] = component_connector(
                    self.ip, conf=conf
                )
            except TimeoutError as e:
                raise TimeoutError(
                    "Could not connect to {} on device {}.".format(
                        component_connector.component_class.get_component_name(),
                        self.ip,
                    )
                )
        return self.connectors[component_connector]


if __name__ == "__main__":
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # allow_agent=False, look_for_keys=False to disable asking for keyring (just use the password)
    ssh.connect(
        "192.168.0.151",
        port=22,
        username="nao",
        password="nao",
        timeout=5,
        allow_agent=False,
        look_for_keys=False,
    )

    # Unzip the file on the remote server
    stdin, stdout, stderr = ssh.exec_command("apt update")

    for i in range(10):
        line = stdout.readline()
        print(line)
        print(stderr.readline())
        # empty line means command is done
        if len(line) == 0:
            break
        time.sleep(1)
