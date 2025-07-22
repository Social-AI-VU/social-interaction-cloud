from __future__ import print_function

import os.path
import tarfile
import tempfile
import threading
import time

from sic_framework.core import sic_logging, utils
from sic_framework.core.connector import SICConnector
from sic_framework.core.sic_redis import SICRedis


class SICLibrary(object):
    """
    A library to be installed on a remote device.
    """

    def __init__(
        self, name, lib_path="", download_cmd="", req_version=None, lib_install_cmd=""
    ):
        self.name = name
        self.lib_path = lib_path
        self.download_cmd = download_cmd
        self.req_version = req_version
        self.lib_install_cmd = lib_install_cmd


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
        """
        Choose specific imports dependend on the type of device.

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

    def __init__(self, ip, sic_version=None, username=None, passwords=None, port=22):
        """
        Connect to the device and ensure an up to date version of the framework is installed
        :param ip: the ip adress of the device
        :param username: the ssh login name
        :param passwords: the (list) of passwords to use
        """
        self._redis = SICRedis()
        self.device_ip = ip
        self._client_id = utils.get_ip_adress()
        self.logger = sic_logging.get_sic_logger(
            name="{}DeviceManager".format(self.__class__.__name__), client_id=self._client_id
        )

        try:
            self.set_reservation()
        except Exception as e:
            self.logger.error("Error setting reservation: {}".format(e))
            raise e

        self.connectors = dict()
        self.configs = dict()
        self.port = port
        self._PING_TIMEOUT = 3
        self.sic_version = sic_version
        self.stop_event = threading.Event()
        self.SCPClient = None

        # if no sic_version is specified, use the same version of the local sic
        if self.sic_version is None:
            from importlib.metadata import version

            self.sic_version = version("social-interaction-cloud")

        try:
            self.SCPClient = SCPClient
        except:
            pass


        self.logger.info("Initializing device with ip: {ip}".format(ip=ip))

        if username is not None:

            if not isinstance(passwords, list):
                passwords = [passwords]

            if not utils.ping_server(self.device_ip, port=self.port, timeout=3):
                raise RuntimeError(
                    "Could not connect to device on ip {}. Please check if it is reachable.".format(
                        self.device_ip
                    )
                )

            self.ssh = paramiko.SSHClient()
            self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            # allow_agent=False, look_for_keys=False to disable asking for keyring (just use the password)
            for p in passwords:
                try:
                    self.ssh.connect(
                        self.device_ip,
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

    def set_reservation(self):
        """
        Set a reservation for the device to prevent other users from using it.
        """
        self.logger.info("Attempting to reserve device {} for client {}".format(self.device_ip, self._client_id))

        # skip reservation for localhost
        if self.device_ip == "localhost" or self.device_ip == "127.0.0.1":
            return True
        
        existing_reservation = self._redis.get_reservation(self.device_ip)
        if existing_reservation is not None:
            self.logger.warning("Device {} is already reserved by another client".format(self.device_ip))
            self.logger.info("Checking if the other client is still connected...")

            # get the client ID who has reserved the device
            other_client_id = existing_reservation
            self.logger.debug("Other client ID: {}".format(other_client_id))

            # check if the other client is still connected
            if other_client_id == self._client_id:
                # no need to reserve the device again
                self.logger.info("Device {} is already reserved by this client".format(self.device_ip))
                return True
            elif self._redis.ping_client(other_client_id) is False:
                self.logger.info("The other client is not connected to SIC, releasing the device")
                self._redis.remove_client(other_client_id)
            else:
                raise Exception("Device {} is already reserved by another client".format(self.device_ip))

        self.logger.info("Reserving device {}".format(self.device_ip))
        reservation_result = self._redis.set_reservation(self.device_ip, self._client_id)
        if reservation_result != 1:
            raise Exception("Reservation for device {} failed: {}".format(self.device_ip, reservation_result))
        else:
            self.logger.info("Device {} has been reserved for this client".format(self.device_ip))

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
        #     if not lib.check_if_lib_installed(remote_libs):
        #         lib.install(self.ssh)

        # Remove signatures from the remote computer
        # add own signature to the remote computer
        self.ssh.exec_command("rm ~/framework/sic_version_signature_*")
        self.ssh.exec_command("touch {}".format(framework_signature))

    def ssh_command(self, command, create_thread=False, **kwargs):
        """
        Executes the given command and logs any errors from the SSH session.

        Args:
            command (str): command to run on ssh client
            **kwargs: Additional keyword arguments to pass to ssh.exec_command
                     (e.g., get_pty=False, timeout=30)

        Returns:
            tuple: (stdin, stdout, stderr) file-like objects from the SSH session

        Raises:
            Various SSH exceptions if connection fails
        """

        try:
            self.logger.debug("Executing command: {command}".format(command=command))
            stdin, stdout, stderr = self.ssh.exec_command(command, **kwargs)

            if create_thread:
                self.logger.debug("Creating thread to monitor remote command")

                def monitor_call():
                    # check if command has exited or if there is standard output
                    while not stdout.channel.exit_status_ready():
                        if stdout.channel.recv_ready():
                            line = stdout.channel.recv(1024).decode("utf-8")
                            self.logger.debug(line)
                    else:
                        # get exit status of the command
                        status = stdout.channel.recv_exit_status()

                        # log exit status and output
                        self.logger.debug(
                            "SSH command exited with status: {status}".format(
                                status=status
                            )
                        )
                        self.logger.debug(
                            "SSH command output: {output}".format(
                                output=stdout.read().decode("utf-8")
                            )
                        )
                        self.logger.debug(
                            "SSH command error: {error}".format(
                                error=stderr.read().decode("utf-8")
                            )
                        )

                        # if remote thread exits before local main thread, report to user.
                        if (
                            threading.main_thread().is_alive()
                            and not self.stop_event.is_set()
                        ):
                            raise RuntimeError(
                                "Remote SIC program has stopped unexpectedly.\nSee sic.log for details"
                            )

                thread = threading.Thread(target=monitor_call)
                thread.name = "remote_SIC_process_monitor"
                thread.start()
                return thread
            else:
                # Check stderr for any errors
                status = stdout.channel.recv_exit_status()
                error_output = stderr.read().decode("utf-8")
                if error_output:
                    self.logger.debug(
                        "SSH command produced errors: {error_output}".format(
                            error_output=error_output
                        )
                    )
                return stdin, stdout, stderr, status

        except paramiko.AuthenticationException as e:
            self.logger.error(
                "Authentication failed when trying to execute ssh command: {e}".format(
                    e=e
                )
            )
            raise
        except paramiko.SSHException as e:
            self.logger.error(
                "SSH exception occurred when trying to execute command: {e}".format(e=e)
            )
            raise
        except Exception as e:
            self.logger.error(
                "Unexpected error while executing ssh command: {e}".format(e=e)
            )
            raise

    def check_if_lib_installed(self, pip_freeze, lib):
        """
        Check to see if a python library name + version is in the 'pip freeze' output of a remote device.
        """
        for cur_lib in pip_freeze:
            cur_lib = cur_lib.replace("\n", "")
            cur_lib_name, cur_lib_ver = cur_lib.split("==")
            if lib.name == cur_lib_name:
                self.logger.debug(
                    "Found package: {} with version {}".format(
                        cur_lib_name, cur_lib_ver
                    )
                )
                # check to make sure version matches if there is a version requirement
                if lib.req_version:
                    if lib.req_version in cur_lib_ver:
                        self.logger.debug(
                            "{} version matches: remote {} == required {}".format(
                                lib.name, cur_lib_ver, lib.req_version
                            )
                        )
                        return True
                    else:
                        self.logger.debug(
                            "{} version mismatch: remote {} != required {}".format(
                                lib.name, cur_lib_ver, lib.req_version
                            )
                        )
                        return False
                return True
        return False

    def install_lib(self, lib):
        """
        Download and install Python library on this remote device
        """
        self.logger.info("Installing {} on remote device ".format(lib.name))

        # download the binary first if necessary, as is the case with Pepper
        if lib.download_cmd:
            stdin, stdout, stderr, exit_status = self.ssh_command(
                """cd {} && {} """.format(lib.lib_path, lib.download_cmd)
            )

            if exit_status != 0:
                err = "".join(stderr.readlines())
                self.logger.error(
                    "Command: cd {} && {} \n Gave error:".format(
                        lib.lib_path, lib.download_cmd
                    )
                )
                self.logger.error(err)
                raise RuntimeError("Error while downloading library on remote device.")

        # install the library
        stdin, stdout, stderr, exit_status = self.ssh_command(
            "cd {} && {}".format(lib.lib_path, lib.lib_install_cmd)
        )

        if "Successfully installed" not in stdout.read().decode():
            err = "".join(stderr.readlines())
            self.logger.error(
                "Command: cd {} && {} \n Gave error:".format(
                    lib.lib_path, lib.lib_install_cmd
                )
            )
            self.logger.error(err)
            raise RuntimeError(
                "Error while installing library on remote device. Please consult manual installation instructions."
            )
        else:
            self.logger.info("Successfully installed {} package".format(lib.name))

    def _get_connector(self, component_connector, **kwargs):
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
                    self.device_ip, conf=conf, **kwargs
                )
            except TimeoutError as e:
                raise TimeoutError(
                    "Could not connect to {} on device {}.".format(
                        component_connector.component_class.get_component_name(),
                        self.device_ip,
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
