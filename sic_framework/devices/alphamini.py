import argparse
import asyncio
import configparser
import os
import socket
from os.path import join
from threading import Thread
from time import sleep

import mini.mini_sdk as MiniSdk
import mini.pkg_tool as Tool

from sic_framework import SICComponentManager
from sic_framework.devices.common_mini.mini_animation import MiniAnimation, MiniAnimationActuator
from sic_framework.devices.device import SICDevice
from sic_framework.devices.common_mini.mini_microphone import MiniMicrophone, MiniMicrophoneSensor
from sic_framework.devices.common_mini.mini_speaker import MiniSpeaker, MiniSpeakerComponent


class Alphamini(SICDevice):
    def __init__(self, ip, mini_id, mini_password, redis_ip, mic_conf=None, speaker_conf=None):
        super().__init__(ip=ip)
        self.mini_id = mini_id
        self.mini_password = mini_password
        self.redis_ip = redis_ip
        self.configs[MiniMicrophone] = mic_conf
        self.configs[MiniSpeaker] = speaker_conf

        # For connecting to alphamini and installing SIC
        MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)
        # self._install_installer()

        if not self._is_ssh_available(host=ip):
            self.install_ssh()
            sleep(30)
            self.install_sic()
            sleep(30)

        thread = Thread(target=self.run_sic)
        thread.start()
        sleep(10)


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
        sleep(10)
        Tool.run_py_pkg("sv-enable ftpd", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("sv up ftpd", robot_id=self.mini_id, debug=True)

        print("The alphamini's ip-address is: ")
        Tool.run_py_pkg("ifconfig", robot_id=self.mini_id, debug=True)
        print('Connect to alphamini with: ssh u0_a25@<ip> -p 8022')

    def install_sic(self):
        print("Installing SIC ...")
        # Install packages for necessary for SIC
        Tool.run_py_pkg("pkg install -y portaudio", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("pkg install -y python-numpy", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("pkg install -y python-pillow", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("pkg install -y sox", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("pkg install -y git", robot_id=self.mini_id, debug=True)

        # Git clone git and checkout mini_device branch
        Tool.run_py_pkg("git clone https://github.com/Social-AI-VU/social-interaction-cloud.git",
                        robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("cd social-interaction-cloud && git checkout mini_device", robot_id=self.mini_id, debug=True)

        # Set-up virtual environment and install pip packages
        Tool.run_py_pkg("python -m venv .venv_sic --system-site-packages",
                        robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg(".venv_sic/bin/python -m pip install --no-input redis six alphamini pyaudio",
                        robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg(
            "cd social-interaction-cloud && ../.venv_sic/bin/python -m pip install --no-input -e .[alphamini]",
            robot_id=self.mini_id, debug=True)

    def run_sic(self):
        print("Running sic on alphamini...")

        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        Tool.run_py_pkg("cd social-interaction-cloud && git pull", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg(f".venv_sic/bin/python social-interaction-cloud/sic_framework/devices/alphamini.py "
                        f"--redis_ip {self.redis_ip} --alphamini_id {self.mini_id}", robot_id=self.mini_id,
                        debug=True)

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
