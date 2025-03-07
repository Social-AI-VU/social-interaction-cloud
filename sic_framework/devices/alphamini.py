import argparse
import os
import socket
import threading
import time

import mini.mini_sdk as MiniSdk
import mini.pkg_tool as Tool

from sic_framework import SICComponentManager
from sic_framework.core.utils import MAGIC_STARTED_COMPONENT_MANAGER_TEXT
from sic_framework.devices.common_mini.mini_animation import MiniAnimation, MiniAnimationActuator
from sic_framework.devices.common_mini.mini_microphone import MiniMicrophone, MiniMicrophoneSensor
from sic_framework.devices.common_mini.mini_speaker import MiniSpeaker, MiniSpeakerComponent
from sic_framework.devices.device import SICDevice


class Alphamini(SICDevice):
    def __init__(self, ip, mini_id, mini_password, redis_ip, username="u0_a25", port=8022, mic_conf=None, speaker_conf=None):
        super().__init__(ip=ip, username=username, passwords=mini_password, port=port)
        self.mini_id = mini_id
        self.mini_password = mini_password
        self.redis_ip = redis_ip
        self.configs[MiniMicrophone] = mic_conf
        self.configs[MiniSpeaker] = speaker_conf
        self.device_path = "/data/data/com.termux/files/home/.venv_sic/lib/python3.12/site-packages/sic_framework/devices/alphamini.py"

        MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

        # Check if ssh is available
        if not self._is_ssh_available(host=ip):
            self.install_ssh()

        if self.check_sic_install():
            print("SIC already installed on the alphamini")
        else:
            print("SIC not installed on the alphamini")
            self.install_sic()

        # this should be blocking to make sure SIC starts on a remote mini before the main thread continues
        self.run_sic()

    @property
    def mic(self):
        return self._get_connector(MiniMicrophone)
    
    @property
    def speaker(self):
        return self._get_connector(MiniSpeaker)

    @property
    def animation(self):
        return self._get_connector(MiniAnimation)

    def install_ssh(self):
        # Updating the package manager
        cmd_source_main = ("echo 'deb https://packages.termux.dev/apt/termux-main stable main' > "
                           "/data/data/com.termux/files/usr/etc/apt/sources.list")
        cmd_source_game = ("echo 'deb https://packages.termux.dev/apt/termux-games games stable' > "
                           "/data/data/com.termux/files/usr/etc/apt/sources.list.d/game.list")
        cmd_source_science = ("echo 'deb https://packages.termux.dev/apt/termux-science science stable' > "
                              "/data/data/com.termux/files/usr/etc/apt/sources.list.d/science.list")
        cmd_source_verify = "head /data/data/com.termux/files/usr/etc/apt/sources.list -n 5"

        print('Updating the sources.list files...')
        Tool.run_py_pkg(cmd_source_main, robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg(cmd_source_game, robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg(cmd_source_science, robot_id=self.mini_id, debug=True)

        print('Verify that the source file has been updated')
        Tool.run_py_pkg(cmd_source_verify, robot_id=self.mini_id, debug=True)

        print('Update the package manager...')
        Tool.run_py_pkg("apt update && apt clean", robot_id=self.mini_id, debug=True)

        # this is necessary otherwise the system pkgs that later `apt` (precisely the https method under `apt`) will link to the old libssl.so.1.1, while
        # apt install -y openssl will install the new libssl.so.3
        # and throw error like "library "libssl.so.1.1" not found"
        print('Upgrade the package manager...')
        # this will prompt the interactive openssl.cnf (Y/I/N/O/D/Z) [default=N] and hang, so pipe 'N' to it to avoid the prompt
        Tool.run_py_pkg("echo 'N' | apt upgrade -y", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("echo 'N' | apt upgrade -y", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("echo 'N' | apt upgrade -y", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("echo 'N' | apt upgrade -y", robot_id=self.mini_id, debug=True)

        print('Installing ssh...')
        # Install openssh
        Tool.run_py_pkg("echo 'N' | apt install -y openssh", robot_id=self.mini_id, debug=True)

        # this is necessary for running ssh-keygen -A, otherwise it will throw CANNOT LINK EXECUTABLE "ssh-keygen": library "libcrypto.so.3" not found
        Tool.run_py_pkg("echo 'N' | apt install -y openssl", robot_id=self.mini_id, debug=True)

        # Set missing host keys
        Tool.run_py_pkg("ssh-keygen -A", robot_id=self.mini_id, debug=True)

        # Set password
        Tool.run_py_pkg(f'echo -e "{self.mini_password}\n{self.mini_password}" | passwd',
                        robot_id=self.mini_id, debug=True)

        # Start ssh and ftp-server
        # The ssh port for mini is 8022
        # ssh u0_a25@ip --p 8022
        Tool.run_py_pkg("sshd", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg('echo "sshd" >> ~/.bashrc', robot_id=self.mini_id, debug=True)

        # install ftp
        # The ftp port for mini is 8021
        Tool.run_py_pkg("pkg install -y busybox termux-services", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("source $PREFIX/etc/profile.d/start-services.sh", robot_id=self.mini_id, debug=True)
        time.sleep(10)
        Tool.run_py_pkg("sv-enable ftpd", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("sv up ftpd", robot_id=self.mini_id, debug=True)

        print("The alphamini's ip-address is: ")
        Tool.run_py_pkg("ifconfig", robot_id=self.mini_id, debug=True)
        print('Connect to alphamini with: ssh u0_a25@<ip> -p 8022')

    def check_sic_install(self):
        """
        Runs a script on Alphamini to see if SIC is installed there
        """
        _, stdout, _ = self.ssh_command(
            """
                    # state if SIC is already installed
                    if [ -d ~/.venv_sic/lib/python3.12/site-packages/sic_framework ]; then
                        echo "SIC already installed";

                        # activate virtual environment if it exists
                        source ~/.venv_sic/bin/activate;

                        # upgrade the social-interaction-cloud package
                        pip install --upgrade social-interaction-cloud --no-deps
                    fi;
                    """
        )

        output = stdout.read().decode()

        if "SIC already installed" in output:
            return True
        else:
            return False

    def is_system_package_installed(self, pkg_name):
        pkg_install_cmd = """
            pkg list-installed | grep -w {pkg_name}
        """.format(
            pkg_name=pkg_name
        )
        _, stdout, _ = self.ssh_command(pkg_install_cmd)
        if "installed" in stdout.read().decode():
            print(f"{pkg_name} is already installed")
            return True
        else:
            return False

    def install_sic(self):
        """
        Run the install script for the Alphamini
        """
        # Check if some system packages are installed
        packages = ["portaudio", "python-numpy", "python-pillow", "git"]
        for pkg in packages:
            if not self.is_system_package_installed(pkg):
                print("Installing package: ", pkg)
                _, stdout, _ = self.ssh_command(f"pkg install -y {pkg}")
                print(stdout.read().decode())

        print("Installing SIC on the Alphamini...")
        print("This may take a while...")
        _, stdout, stderr = self.ssh_command(
            """
                # create virtual environment
                rm -rf .venv_sic
                python -m venv .venv_sic --system-site-packages;
                source ~/.venv_sic/bin/activate;

                # install required packages and perform a clean sic installation
                pip install social-interaction-cloud --no-deps;
                pip install redis six pyaudio alphamini websockets==13.1 protobuf==3.20.3

                """
        )

        output = stdout.read().decode()
        error = stderr.read().decode()

        if not "Successfully installed social-interaction-cloud" in output:
            raise Exception(
                "Failed to install sic. Standard error stream from install command: {}".format(
                    error
                )
            )
        else:
            print("SIC successfully installed")

    def run_sic(self):
        print("Running sic on alphamini...")


        self.stop_cmd = """
            echo 'Killing all previous robot wrapper processes';
            pkill -f "python {alphamini_device}"
        """.format(alphamini_device=self.device_path)

        # stop alphamini
        print("killing processes")
        self.ssh.exec_command(self.stop_cmd)
        time.sleep(1)

        self.start_cmd = """
            source .venv_sic/bin/activate;
            python {alphamini_device} --redis_ip={redis_ip} --alphamini_id {mini_id};
        """.format(
            alphamini_device= self.device_path, redis_ip=self.redis_ip, mini_id=self.mini_id
        )
        print("starting SIC on alphamini")
        # start alphamini
        _, stdout, _ = self.ssh.exec_command(self.start_cmd, get_pty=False)

        stdout.channel.set_combine_stderr(True)

        # # # TODO move the remote SIC process monitoring and logging to SICDevice
        self.logfile = open("sic.log", "w")

        # Set up error monitoring
        self.stopping = False

        def check_if_exit():
            # wait for the process to exit
            status = stdout.channel.recv_exit_status()
            # if remote threads exits before local main thread, report to user.
            if threading.main_thread().is_alive() and not self.stopping:
                self.logfile.flush()
                raise RuntimeError(
                    "Remote SIC program has stopped unexpectedly.\nSee sic.log for details"
                )

        # Start monitoring thread
        exit_thread = threading.Thread(target=check_if_exit, name="remote_SIC_process_monitor")
        exit_thread.start()

        # Wait for SIC to start
        for i in range(300):
            line = stdout.readline()
            self.logfile.write(line)
            self.logfile.flush()

            if MAGIC_STARTED_COMPONENT_MANAGER_TEXT in line:
                print("SIC started successfully.")
                break
            time.sleep(0.01)
        else:
            raise RuntimeError("Could not start SIC on remote device\nSee sic.log for details")

        # Write remaining logs in the background
        def write_logs():
            for line in stdout:
                self.logfile.write(line)
                self.logfile.flush()
                if not threading.main_thread().is_alive() or self.stopping:
                    break

        log_thread = threading.Thread(target=write_logs, name="remote_SIC_process_log_writer")
        log_thread.start()

    def __del__(self):
        if hasattr(self, "logfile"):
            self.logfile.close()

    @staticmethod
    def _is_ssh_available(host, port=8022, timeout=5):
        """
        Check if an SSH connection is possible by testing if the port is open.

        :param host: SSH server hostname or IP
        :param port: SSH port (default 22)
        :param timeout: Timeout for connection attempt (default 5 seconds)
        :return: True if SSH connection is possible, False otherwise
        """
        try:
            with socket.create_connection((host, port), timeout):
                return True
        except (socket.timeout, socket.error):
            return False


# mini_component_list = [MiniMicrophoneSensor, MiniSpeakerComponent, MiniAnimationActuator]
mini_component_list = [MiniSpeakerComponent, MiniAnimationActuator]


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis_ip", type=str, required=True, help="IP address where Redis is running"
    )
    parser.add_argument(
        "--alphamini_id", type=str, required=True, help="Provide the last 5 digits of the robot's serial number"
    )
    args = parser.parse_args()

    os.environ["DB_IP"] = args.redis_ip
    os.environ["ALPHAMINI_ID"] = args.alphamini_id
    SICComponentManager(mini_component_list)
