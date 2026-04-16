import argparse
import asyncio
import enum
import os
import socket
import threading
import time
from concurrent.futures import Future

import mini.mini_sdk as MiniSdk
import mini.pkg_tool as Tool
from mini import MouthLampColor, MouthLampMode
from mini.apis.api_action import GetActionList, PlayAction, RobotActionType
from mini.apis.api_expression import PlayExpression, SetMouthLamp

from sic_framework import SICComponentManager
from sic_framework.core import utils
from sic_framework.core.message_python2 import SICPingRequest, SICPongMessage, SICStopServerRequest
from sic_framework.core.utils import MAGIC_STARTED_COMPONENT_MANAGER_TEXT
from sic_framework.devices.common_mini.mini_camera import (
    MiniCamera,
    MiniCameraSensor,
)
from sic_framework.devices.common_mini.mini_microphone import (
    MiniMicrophone,
    MiniMicrophoneSensor,
)
from sic_framework.devices.common_mini.mini_speaker import (
    MiniSpeaker,
    MiniSpeakerComponent,
)
from sic_framework.devices.device import SICDeviceManager
from sic_framework.core.exceptions import DeviceInstallationError, DeviceExecutionError


@enum.unique
class SDKAnimationType(enum.Enum):
    ACTION = "action"
    EXPRESSION = "expression"


class WiFiDevice:
    """
    WifiDevice class that the MiniSdk.connect() method expects. Taken from mini/mini_sdk.py. Only the ip address is relevant
    """
    def __init__(self, name: str = "", address: str = "localhost", port: int = -1, s_type: str = "", server: str = ""):
        super().__init__()
        self.address = address
        self.port = port
        self.type = s_type
        self.server = server

        if name.endswith(s_type):
            self.name = name[: -(len(s_type) + 1)]
        else:
            self.name = name

    def __repr__(self):
        return str(self.__class__) + " name:" + self.name + " address:" + self.address + " port:" + str(
            self.port) + " type:" + self.type + " server:" + self.server

class Alphamini(SICDeviceManager):
    def __init__(
        self,
        ip,
        mini_id,
        mini_password,
        redis_ip,
        username="u0_a25",
        port=8022,
        mic_conf=None,
        speaker_conf=None,
        camera_conf=None,
        dev_test=False,
        sdk_test_mode=False,
        test_repo=None,
        bypass_install=False,
        sic_version=None,
        tailscale_authkey=None,
    ):
        """
        Initialize the Alphamini device.
        :param ip: IP address of the Alphamini
        :param mini_id: The last 5 digits of the Alphamini's serial number
        :param mini_password: The password for the Alphamini
        :param redis_ip: The IP address of the Redis server
        :param username: The username for SSH (default: u0_a25)
        :param port: The SSH port (default: 8022)
        :param mic_conf: Configuration for the microphone
        :param speaker_conf: Configuration for the speaker
        :param dev_test: If True, use the test environment (default: False)
        :param test_repo: Path to the test repository (default: None)
        :param bypass_install: If True, skip the installation of SIC (default: False)
        :param sic_version: Version of SIC to install on the Alphamini (default: None,which uses the same version as your local environment.

        """
        self.mini_id = mini_id
        self.mini_ip = ip
        self.mini_password = mini_password
        self.redis_ip = redis_ip
        self.dev_test = dev_test
        self.sdk_test_mode = sdk_test_mode
        self.bypass_install = bypass_install
        self.test_repo = test_repo
        self._mini_api = None
        self._sdk_animation_futures = []
        self._sdk_loop = None
        self._sdk_loop_thread = None
        self.tailscale_authkey = tailscale_authkey

        # Module path for the Alphamini device script. We invoke it via
        # "python -m sic_framework.devices.alphamini" on the robot, so we do not
        # depend on a specific Python minor version or site-packages path.
        self.device_module = "sic_framework.devices.alphamini"

        MiniSdk.set_robot_type(MiniSdk.RobotType.EDU)

        # Check if ssh is available. If the port is closed, first try a light
        # recovery by restarting sshd before falling back to full re-install.
        if not self._is_ssh_available(host=ip, port=port):
            if not self._try_recover_ssh_daemon(host=ip, port=port):
                self.install_ssh()

        # only after ssh is available, we can initialize the SICDeviceManager
        super().__init__(
            ip=ip,
            username=username,
            passwords=mini_password,
            port=port,
            sic_version=sic_version,
        )
        self.logger.info("SIC version on your local machine: {version}".format(version=self.sic_version))
        self.configs[MiniMicrophone] = mic_conf
        self.configs[MiniSpeaker] = speaker_conf
        self.configs[MiniCamera] = camera_conf

        # If Tailscale is explicitly enabled (or already on the robot), ensure it's set up
        use_tailscale = os.environ.get("USE_TAILSCALE", "").lower() in ("1", "true", "yes")
        _, stdout, _, _ = self.ssh_command(
            "[ -x ~/tailscale/tailscale ] && echo 'ts_yes' || echo 'ts_no'"
        )
        ts_installed = "ts_yes" in stdout.read().decode()
        if use_tailscale and (self.tailscale_authkey or ts_installed):
            self.install_tailscale()
            _, stdout, _, _ = self.ssh_command(
                "~/tailscale/tailscale --socket ~/tailscale/tailscaled.sock ip -4"
            )
            ts_ip = stdout.read().decode().strip()
            if ts_ip:
                self.device_ip = ts_ip

        if self.dev_test:
            self.create_test_environment()
        else:
            if self.bypass_install or self.check_sic_install():
                self.logger.info("SIC already installed on the alphamini")
            else:
                self.logger.info("SIC not installed on the alphamini")
                self.install_sic()

        # this should be blocking to make sure SIC starts on a remote mini before the main thread continues
        self.run_sic()
        self._initialize_mini_sdk_controls()

    def _initialize_mini_sdk_controls(self):
        """
        Initialize a background asyncio loop and connect to MiniSDK once.

        If this fails, SIC connectors still work; SDK control methods will raise
        until a successful reconnect.
        """
        if self.sdk_test_mode:
            self.logger.info("MiniSDK test mode is enabled; SDK control calls are no-op.")
            return

        self._sdk_loop = asyncio.new_event_loop()
        self._sdk_loop_thread = threading.Thread(target=self._run_sdk_loop, daemon=True)
        self._sdk_loop_thread.start()
        try:
            self.connect_mini_sdk()
        except Exception as e:
            self.logger.warning("MiniSDK control channel is not available yet: %s", e)

    def _run_sdk_loop(self):
        asyncio.set_event_loop(self._sdk_loop)
        self._sdk_loop.run_forever()

    def _require_sdk_loop(self):
        if not self._sdk_loop or not self._sdk_loop.is_running():
            raise DeviceExecutionError("MiniSDK loop is not running")

    def connect_mini_sdk(self, timeout: int = 10):
        """
        Connect this Alphamini device to the Mini SDK control channel.
        """
        if self.sdk_test_mode:
            self.logger.debug("connect_mini_sdk called in sdk_test_mode.")
            return None
        self._require_sdk_loop()
        fut = asyncio.run_coroutine_threadsafe(self._connect_mini_sdk_once(timeout=timeout), self._sdk_loop)
        return fut.result()

    async def _connect_mini_sdk_once(self, timeout: int = 10):
        if not self._mini_api:
            self._mini_api = WiFiDevice(name=self.mini_id, address=self.mini_ip)
            await MiniSdk.connect(self._mini_api)
        return self._mini_api

    def disconnect_mini_sdk(self):
        """
        Release the Mini SDK control channel.
        """
        if self.sdk_test_mode:
            self.logger.debug("disconnect_mini_sdk called in sdk_test_mode.")
            return None
        if not self._sdk_loop or not self._sdk_loop.is_running():
            return
        fut = asyncio.run_coroutine_threadsafe(self._disconnect_mini_sdk(), self._sdk_loop)
        return fut.result()

    async def _disconnect_mini_sdk(self):
        await MiniSdk.release()
        self._mini_api = None

    async def _play_action(self, action_name: str):
        async def command():
            action = PlayAction(action_name=action_name)
            return await action.execute()

        return await self._execute_with_reconnect(command, action_name)

    async def _play_expression(self, expression_name: str):
        async def command():
            expression = PlayExpression(express_name=expression_name)
            return await expression.execute()

        return await self._execute_with_reconnect(command, expression_name)

    def animate(self, animation_type, animation_id: str, run_async: bool = False):
        """
        Unified SDK wrapper for action/expression controls.

        animation_type supports:
        - SDKAnimationType.ACTION / SDKAnimationType.EXPRESSION
        - "action" / "expression" (case-insensitive)
        """
        normalized_type = self._normalize_animation_type(animation_type)
        if self.sdk_test_mode:
            self.logger.info("MiniSDK test mode: animate(type=%s, id=%s)", normalized_type.value, animation_id)
            return self._test_mode_result(run_async)

        self._require_sdk_loop()
        target_coro = self._play_action(animation_id) if normalized_type == SDKAnimationType.ACTION else self._play_expression(animation_id)
        fut = asyncio.run_coroutine_threadsafe(target_coro, self._sdk_loop)
        self._sdk_animation_futures.append(fut)
        if not run_async:
            return fut.result()
        return fut

    def set_mouth_lamp(
        self,
        color: MouthLampColor,
        mode: MouthLampMode,
        duration: int = -1,
        breath_duration: int = 1000,
        run_async: bool = False,
    ):
        """
        Set AlphaMini mouth lamp color/mode.
        """
        if self.sdk_test_mode:
            self.logger.info(
                "MiniSDK test mode: set_mouth_lamp(color=%s, mode=%s, duration=%s, breath_duration=%s)",
                color,
                mode,
                duration,
                breath_duration,
            )
            return self._test_mode_result(run_async)
        self._require_sdk_loop()
        fut = asyncio.run_coroutine_threadsafe(
            self._set_mouth_lamp(color, mode, duration, breath_duration),
            self._sdk_loop,
        )
        self._sdk_animation_futures.append(fut)
        if not run_async:
            return fut.result()
        return fut

    async def _set_mouth_lamp(
        self,
        color: MouthLampColor,
        mode: MouthLampMode,
        duration: int = -1,
        breath_duration: int = 1000,
    ):
        async def command():
            if mode == MouthLampMode.BREATH:
                action = SetMouthLamp(color=color, mode=MouthLampMode.BREATH, breath_duration=breath_duration)
            else:
                action = SetMouthLamp(color=color, mode=MouthLampMode.NORMAL, duration=duration)
            return await action.execute()

        return await self._execute_with_reconnect(command, "mouth_lamp")

    async def _execute_with_reconnect(self, command_factory, command_name: str):
        await self._connect_mini_sdk_once()
        try:
            return await command_factory()
        except Exception as first_error:
            self.logger.warning("MiniSDK command '%s' failed, reconnecting once: %s", command_name, first_error)
            try:
                await self._disconnect_mini_sdk()
            except Exception:
                pass
            await self._connect_mini_sdk_once()
            return await command_factory()

    @staticmethod
    def _normalize_animation_type(animation_type):
        if isinstance(animation_type, SDKAnimationType):
            return animation_type
        if isinstance(animation_type, str):
            normalized = animation_type.strip().lower()
            if normalized == SDKAnimationType.ACTION.value:
                return SDKAnimationType.ACTION
            if normalized == SDKAnimationType.EXPRESSION.value:
                return SDKAnimationType.EXPRESSION
        raise DeviceExecutionError(
            f"Unsupported animation_type '{animation_type}'. Use SDKAnimationType or 'action'/'expression'."
        )

    @staticmethod
    def _test_mode_result(run_async: bool):
        if run_async:
            completed = Future()
            completed.set_result(None)
            return completed
        return None

    @property
    def mic(self):
        return self._get_connector(MiniMicrophone)

    @property
    def speaker(self):
        return self._get_connector(MiniSpeaker)

    @property
    def camera(self):
        return self._get_connector(MiniCamera)

    def _try_recover_ssh_daemon(self, host, port=8022):
        print(
            "SSH port {port} is unreachable on {host}. Attempting lightweight recovery before reinstall...".format(
                port=port, host=host
            )
        )

        # First, run a simple command through the py-pkg path. On some robots
        # this is enough to trigger shell init that brings sshd back.
        probe_command = "if echo sic_probe >/dev/null 2>&1; then exit 0; else exit 41; fi"
        try:
            Tool.run_py_pkg(probe_command, robot_id=self.mini_id, debug=True)
            time.sleep(2)
            if self._is_ssh_available(host=host, port=port):
                print("SSH became available after lightweight run_py_pkg probe.")
                return True
        except Exception:
            pass

        # Retry once more before attempting explicit daemon restart.
        try:
            Tool.run_py_pkg(probe_command, robot_id=self.mini_id, debug=True)
            time.sleep(2)
            if self._is_ssh_available(host=host, port=port):
                print("SSH became available after second run_py_pkg probe.")
                return True
        except Exception:
            pass

        # SSH is likely not installed or misconfigured. Fall back to full reinstall.
        return False

    def install_ssh(self):
        # Updating the package manager
        cmd_source_main = (
            "echo 'deb https://packages.termux.dev/apt/termux-main stable main' > "
            "/data/data/com.termux/files/usr/etc/apt/sources.list"
        )
        cmd_source_game = (
            "echo 'deb https://packages.termux.dev/apt/termux-games games stable' > "
            "/data/data/com.termux/files/usr/etc/apt/sources.list.d/game.list"
        )
        cmd_source_science = (
            "echo 'deb https://packages.termux.dev/apt/termux-science science stable' > "
            "/data/data/com.termux/files/usr/etc/apt/sources.list.d/science.list"
        )
        cmd_source_verify = (
            "head /data/data/com.termux/files/usr/etc/apt/sources.list -n 5"
        )

        print("Updating the sources.list files...")
        Tool.run_py_pkg(cmd_source_main, robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg(cmd_source_game, robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg(cmd_source_science, robot_id=self.mini_id, debug=True)

        print("Verifying that the source file has been updated")
        Tool.run_py_pkg(cmd_source_verify, robot_id=self.mini_id, debug=True)

        print("Update the package manager...")
        Tool.run_py_pkg("apt update && apt clean", robot_id=self.mini_id, debug=True)

        # this is necessary otherwise the system pkgs that later `apt` (precisely the https method under `apt`) will link to the old libssl.so.1.1, while
        # apt install -y openssl will install the new libssl.so.3
        # and throw error like "library "libssl.so.1.1" not found"
        print("Upgrade the package manager...")
        # this will prompt the interactive openssl.cnf (Y/I/N/O/D/Z) [default=N] and hang, so pipe 'N' to it to avoid the prompt
        Tool.run_py_pkg("echo 'N' | apt upgrade -y", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("echo 'N' | apt upgrade -y", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("echo 'N' | apt upgrade -y", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("echo 'N' | apt upgrade -y", robot_id=self.mini_id, debug=True)

        print("Installing ssh...")
        # Install openssh
        Tool.run_py_pkg(
            "echo 'N' | apt install -y openssh", robot_id=self.mini_id, debug=True
        )

        # this is necessary for running ssh-keygen -A, otherwise it will throw CANNOT LINK EXECUTABLE "ssh-keygen": library "libcrypto.so.3" not found
        Tool.run_py_pkg(
            "echo 'N' | apt install -y openssl", robot_id=self.mini_id, debug=True
        )

        # Set missing host keys
        Tool.run_py_pkg("ssh-keygen -A", robot_id=self.mini_id, debug=True)

        # Set password
        Tool.run_py_pkg(
            f'echo -e "{self.mini_password}\n{self.mini_password}" | passwd',
            robot_id=self.mini_id,
            debug=True,
        )

        # Start ssh and ftp-server
        # The ssh port for mini is 8022
        # ssh u0_a25@ip --p 8022
        Tool.run_py_pkg("sshd", robot_id=self.mini_id, debug=True)
        # only add sshd to bashrc if it's not there
        Tool.run_py_pkg(
            "grep -q 'sshd' ~/.bashrc || echo 'sshd' >> ~/.bashrc",
            robot_id=self.mini_id,
            debug=True,
        )

        # install ftp
        # The ftp port for mini is 8021
        Tool.run_py_pkg(
            "pkg install -y busybox termux-services", robot_id=self.mini_id, debug=True
        )
        Tool.run_py_pkg(
            "source $PREFIX/etc/profile.d/start-services.sh",
            robot_id=self.mini_id,
            debug=True,
        )
        time.sleep(10)
        Tool.run_py_pkg("sv-enable ftpd", robot_id=self.mini_id, debug=True)
        Tool.run_py_pkg("sv up ftpd", robot_id=self.mini_id, debug=True)

        print("The alphamini's ip-address is: ")
        Tool.run_py_pkg("ifconfig", robot_id=self.mini_id, debug=True)
        print("Connect to alphamini with: ssh u0_a25@<ip> -p 8022")

    def check_sic_install(self):
        """
        Runs a script on Alphamini to see if SIC is installed there
        """
        _, stdout, _, exit_status = self.ssh_command(
            """
                    # state if SIC is already installed
                    if [ -d ~/.venv_sic ]; then
                        # activate virtual environment if it exists
                        source ~/.venv_sic/bin/activate;

                        # check if sic_framework is importable in this venv
                        python -c "import sic_framework" >/dev/null 2>&1 && {{
                            echo "SIC already installed";

                            # upgrade the social-interaction-cloud package
                            pip install --upgrade social-interaction-cloud=={version} --no-deps;
                        }}
                    fi;
                    """.format(
                version=self.sic_version
            )
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
        _, stdout, _, exit_status = self.ssh_command(pkg_install_cmd)
        if "installed" in stdout.read().decode():
            self.logger.info("{pkg_name} is already installed".format(pkg_name=pkg_name))
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
                self.logger.info("Installing package: {pkg}".format(pkg=pkg))
                _, stdout, _, exit_status = self.ssh_command("pkg install -y {pkg}".format(pkg=pkg))
                self.logger.info(stdout.read().decode())

        self.logger.info("Installing SIC on the Alphamini...")
        self.logger.info("This may take a while...")
        _, stdout, stderr, exit_status = self.ssh_command(
            """
                # create virtual environment
                rm -rf .venv_sic
                python -m venv .venv_sic --system-site-packages;
                source ~/.venv_sic/bin/activate;

                # install required packages and perform a clean sic installation
                pip install social-interaction-cloud=={version} --no-deps;
                pip install redis six pyaudio alphamini websockets==13.1 protobuf==3.20.3

                """.format(
                version=self.sic_version
            )
        )

        output = stdout.read().decode()
        error = stderr.read().decode()

        if not "Successfully installed social-interaction-cloud" in output:
            raise DeviceInstallationError(
                "Failed to install sic. Standard error stream from install command: {}".format(
                    error
                )
            )
        else:
            self.logger.info("SIC successfully installed")

    def install_tailscale(self):
        """
        Install, start, and authenticate Tailscale in userspace mode on the robot.
        """
        # Install binary if missing
        self.ssh_command(
            """
            if [ ! -x ~/tailscale/tailscale ]; then
                pkg install -y wget socat
                mkdir -p ~/tailscale && cd ~/tailscale
                wget -q https://pkgs.tailscale.com/stable/tailscale_1.96.4_arm64.tgz
                tar xzf tailscale_1.96.4_arm64.tgz --strip-components=1
                rm -f tailscale_1.96.4_arm64.tgz
            fi
            mkdir -p ~/.tailscale_state
            """
        )

        # Check if daemon is already running with the correct socket
        _, stdout, _, _ = self.ssh_command(
            "pgrep -f tailscaled > /dev/null 2>&1 && [ -S ~/tailscale/tailscaled.sock ] && echo ok"
        )
        daemon_running = "ok" in stdout.read().decode()

        if not daemon_running:
            self.ssh_command("pkill -f tailscaled || true; rm -f ~/tailscale/tailscaled.sock")
            time.sleep(1)
            # Start daemon in its own thread (same pattern as run_sic for SIC)
            self.ssh_command(
                "cd ~/tailscale && ./tailscaled --tun=userspace-networking "
                "--socks5-server=localhost:1055 "
                "--statedir=$HOME/.tailscale_state "
                "--socket=$HOME/tailscale/tailscaled.sock "
                "> ~/tailscale/tailscaled.log 2>&1",
                create_thread=True, get_pty=False
            )
            # Wait up to 10s for socket to appear
            for _ in range(10):
                _, stdout, _, _ = self.ssh_command("[ -S ~/tailscale/tailscaled.sock ] && echo ok")
                if "ok" in stdout.read().decode():
                    break
                time.sleep(1)
            else:
                raise DeviceInstallationError(
                    "Tailscale daemon failed to start. Check ~/tailscale/tailscaled.log"
                )

        # Check auth state
        _, stdout, _, _ = self.ssh_command(
            "~/tailscale/tailscale --socket ~/tailscale/tailscaled.sock status >/dev/null 2>&1 && echo ok"
        )
        authenticated = "ok" in stdout.read().decode()

        if not authenticated:
            if not self.tailscale_authkey:
                raise DeviceInstallationError(
                    "Tailscale is not authenticated and no tailscale_authkey provided. "
                    "Generate one at https://login.tailscale.com/admin/settings/keys"
                )
            self.logger.info("Authenticating Tailscale with auth key...")
            _, stdout, _, _ = self.ssh_command(
                "~/tailscale/tailscale --socket ~/tailscale/tailscaled.sock up --authkey {key} 2>&1".format(
                    key=self.tailscale_authkey
                )
            )
            self.logger.info("tailscale up output: {}".format(stdout.read().decode()))
            # Verify auth succeeded
            _, stdout, _, _ = self.ssh_command(
                "~/tailscale/tailscale --socket ~/tailscale/tailscaled.sock status >/dev/null 2>&1 && echo ok"
            )
            if "ok" not in stdout.read().decode():
                raise DeviceInstallationError(
                    "Tailscale authentication failed. The auth key may be invalid, "
                    "expired, or already consumed. Generate a new one at "
                    "https://login.tailscale.com/admin/settings/keys"
                )
            self.logger.info("Tailscale authenticated successfully")
        else:
            self.logger.info("Tailscale already authenticated")

    def _configure_tailscale_env(self, venv_name):
        """Add Tailscale env vars to a venv's activate script (no-op if venv missing)."""
        self.ssh_command(
            """
            ACT=~/{venv}/bin/activate
            [ -f "$ACT" ] && ! grep -q 'USE_TAILSCALE' "$ACT" && cat >> "$ACT" << 'EOF'
export PATH="$HOME/tailscale:$PATH"
export TS_SOCKET="$HOME/tailscale/tailscaled.sock"
export USE_TAILSCALE=1
EOF
            true
            """.format(venv=venv_name)
        )

    def _ensure_socat_bridge(self):
        """Start a socat bridge so Redis on robot's 127.0.0.1:6379 tunnels to the host's Tailscale IP."""
        # Get this host's Tailscale IP (the machine running SIC)
        ts_host_ip = utils.get_ip_adress()
        if not ts_host_ip.startswith("100."):
            return  # Not a Tailscale IP, skip
        self.ssh_command(
            """
            if [ -x ~/tailscale/tailscale ]; then
                pkill -f socat || true
                sleep 1
                nohup socat TCP4-LISTEN:6379,bind=127.0.0.1,reuseaddr,fork \
                    SOCKS5:127.0.0.1:{ts_host_ip}:6379,socksport=1055 > ~/socat_redis.log 2>&1 &
            fi
            """.format(ts_host_ip=ts_host_ip)
        )

    def create_test_environment(self):
        """
        Creates a test environment on the Alphamini

        To use test environment, you must pass in a repo to the device initialization. For example:
        
        - Mini(ip, mini_id, mini_password, redis_ip, dev_test=True, test_repo=PATH_TO_REPO) OR
        - Mini(ip, mini_id, mini_password, redis_ip, dev_test=True)

        If you do not pass in a repo, it will assume the repo to test is already installed in a test environment on the Alphamini.

        This function:
        
        - checks to see if test environment exists
        - if test_venv exists and no repo is passed in (self.test_repo), return True (no need to do anything)
        - if test_venv exists but a new repo has been passed in:
        
          1. uninstall old version of social-interaction-cloud on Alphamini
          2. zip the provided repo
          3. scp zip file over to alphamini, to 'sic_to_test' folder
          4. unzip repo and install
          
        - if test_venv does not exist:
        
          1. check to make sure a test repo has been passed in to device initialization. If not, raise RuntimeError
          2. if repo has been passed in, create a new .test_venv and install repo
        """

        def init_test_venv():
            """
            Initialize a new test virtual environment
            """
            # start with a clean slate just to be sure
            _, stdout, _, exit_status = self.ssh_command(
                    """
                    rm -rf ~/.test_venv

                    # create virtual environment
                    python -m venv .test_venv --system-site-packages;
                    source ~/.test_venv/bin/activate;

                    # install required packages and perform a clean sic installation
                    pip install PyTurboJPEG redis six pyaudio alphamini websockets==13.1 protobuf==3.20.3
                    """
                )

            # test to make sure the virtual environment was created and that key
            # packages can be imported
            _, _, _, exit_status = self.ssh_command(
                """
                source ~/.test_venv/bin/activate;
                """
            )
            if exit_status != 0:
                raise DeviceInstallationError(
                    "Failed to create test virtual environment with required packages "
                )

        def uninstall_old_repo():
            """
            Uninstall the old version of social-interaction-cloud on Alphamini
            """
            _, stdout, _, exit_status = self.ssh_command(
                """
                source ~/.test_venv/bin/activate;
                pip uninstall social-interaction-cloud -y
                """
            )

        def install_new_repo():
            """
            Install the new repo on Alphamini
            """
            self.logger.info("Zipping up dev repo")
            zipped_path = utils.zip_directory(self.test_repo)

            # get the basename of the repo
            repo_name = os.path.basename(self.test_repo)

            # create the sic_in_test folder on Mini
            _, stdout, _, exit_status = self.ssh_command(
                """
                cd ~;
                rm -rf sic_in_test;
                mkdir sic_in_test;
                """.format(
                    repo_name=repo_name
                )
            )

            self.logger.info("Transferring zip file over to Mini")

            # Use SFTP instead of SCP to avoid Android FORTIFY umask issue
            sftp = self.ssh.open_sftp()
            remote_path = "/data/data/com.termux/files/home/sic_in_test/" + os.path.basename(zipped_path)
            sftp.put(zipped_path, remote_path)
            sftp.close()

            _, stdout, _, exit_status = self.ssh_command(
                """
                source ~/.test_venv/bin/activate;
                cd /data/data/com.termux/files/home/sic_in_test/;
                unzip {repo_name};
                cd {repo_name};
                pip install -e . --no-deps;
                """.format(
                    repo_name=repo_name
                )
            )

            # check to see if the repo was installed successfully
            if exit_status != 0:
                raise DeviceInstallationError("Failed to install social-interaction-cloud")

        # check to see if test environment already exists
        _, stdout, _, exit_status = self.ssh_command(
            """
            source ~/.test_venv/bin/activate;
            """
        )

        # if the environment can be activated, also verify that key Python
        # packages are importable. If imports fail, we treat the environment
        # as broken and re-initialise it.
        pkg_status = 1
        if exit_status == 0:
            _, _, _, pkg_status = self.ssh_command(
                """
                source ~/.test_venv/bin/activate;
                python -c "import sic_framework" && python -c "import mini"
                """
            )

        if exit_status == 0 and pkg_status == 0 and not self.test_repo:
            self.logger.info(
                "Test environment already created on Mini with required packages present "
                "and no new dev repo provided... skipping test_venv setup"
            )
            return True
        elif exit_status == 0 and pkg_status == 0 and self.test_repo:
            self.logger.info(
                "Test environment already created on Mini and new dev repo provided... uninstalling old repo and installing new one"
            )
            self.logger.warning(
                "This process may take a minute or two... Please hold tight!"
            )
            uninstall_old_repo()
            install_new_repo()
        elif (exit_status == 0 and pkg_status != 0) and self.test_repo:
            # environment exists but is missing required packages
            self.logger.info(
                "Test environment on Mini is missing required packages... reinitialising test environment and installing new repo"
            )
            self.logger.warning(
                "This process may take a minute or two... Please hold tight!"
            )
            init_test_venv()
            install_new_repo()
        elif (exit_status == 0 and pkg_status != 0) and not self.test_repo:
            self.logger.error(
                "Test environment on Mini is missing required packages and no new dev repo provided... raising RuntimeError"
            )
            raise DeviceInstallationError(
                "Need to provide repo to recreate broken test environment"
            )
        elif exit_status == 1 and self.test_repo:
            # test environment not created, so create one
            self.logger.info(
                "Test environment not created on Mini and new dev repo provided... creating test environment and installing new repo"
            )
            self.logger.warning(
                "This process may take a minute or two... Please hold tight!"
            )
            init_test_venv()
            install_new_repo()
        elif exit_status == 1 and not self.test_repo:
            self.logger.error(
                "No test environment present on Mini and no new dev repo provided... raising RuntimeError"
            )
            raise DeviceInstallationError("Need to provide repo to create test environment")
        else:
            self.logger.error(
                "Activating test environment on Mini resulted in unknown exit status: {}".format(
                    exit_status
                )
            )
            raise DeviceInstallationError(
                "Unknown error occurred while creating test environment on Mini"
            )

    def run_sic(self):
        self.logger.info("Running sic on alphamini...")
        self._configure_tailscale_env(".venv_sic")
        self._configure_tailscale_env(".test_venv")
        self._ensure_socat_bridge()

        self.stop_cmd = """
            echo 'Killing all previous robot wrapper processes';
            # pkill returns 1 when no process matched; treat that as success.
            pkill -f "python -m {alphamini_module}" || true
        """.format(
            alphamini_module=self.device_module
        )

        # stop alphamini
        self.logger.info("Killing previously running SIC processes")
        self.ssh_command(self.stop_cmd)
        time.sleep(1)

        self.start_cmd = """
            python -m {alphamini_module} --redis_ip={redis_ip} --client_id {client_id} --alphamini_id {mini_id};
        """.format(
            alphamini_module=self.device_module,
            redis_ip=self.redis_ip,
            client_id=self._client_id,
            mini_id=self.mini_id,
        )

        # if this is a dev test, we want to use the test environment instead.
        if self.dev_test:
            self.logger.debug("Using developer test environment...")
            self.start_cmd = (
                """
                source .test_venv/bin/activate;
            """
                + self.start_cmd
            )
        else:
            self.start_cmd = (
                """
                source .venv_sic/bin/activate;
            """
                + self.start_cmd
            )

        self.logger.info("starting SIC on alphamini")

        # start alphamini
        self.ssh_command(self.start_cmd, create_thread=True, get_pty=False)

        self.logger.info("Pinging ComponentManager on Alphamini")

        # Wait for SIC to start
        ping_tries = 5
        for i in range(ping_tries):
            try:
                response = self._redis.request(
                    self.device_ip, SICPingRequest(), timeout=self._PING_TIMEOUT, block=True
                )
                if response == SICPongMessage():
                    self.logger.info(
                        "ComponentManager on ip {} has started!".format(self.device_ip)
                    )
                    break
            except TimeoutError:
                self.logger.debug(
                    "ComponentManager on ip {} hasn't started yet... retrying ping {} more times".format(
                        self.device_ip, ping_tries - 1 - i
                    )
                )
        else:
            raise DeviceExecutionError(
                "Could not start SIC on remote device\nSee SIC logs for details"
            )

    def __del__(self):
        if hasattr(self, "logfile"):
            self.logfile.close()

    def stop_device(self):
        """
        Stops the device and all its components.

        Makes sure the process is killed and the device is stopped.
        """
        # send StopRequest to ComponentManager
        self._redis.request(self.device_ip, SICStopServerRequest(), block=False)

        # stop pending Mini SDK actions and release SDK resources
        for fut in self._sdk_animation_futures:
            fut.cancel()
        self._sdk_animation_futures = []
        try:
            self.disconnect_mini_sdk()
        except Exception:
            pass
        if self._sdk_loop and self._sdk_loop.is_running():
            self._sdk_loop.call_soon_threadsafe(self._sdk_loop.stop)
        if self._sdk_loop_thread:
            self._sdk_loop_thread.join(timeout=2)


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


mini_component_list = [
    MiniMicrophoneSensor,
    MiniSpeakerComponent,
    MiniCameraSensor,
]


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis_ip", type=str, required=True, help="IP address where Redis is running"
    )
    parser.add_argument(
        "--client_id", type=str, required=True, help="Client that is using this device"
    )
    parser.add_argument(
        "--alphamini_id",
        type=str,
        required=True,
        help="Provide the last 5 digits of the robot's serial number",
    )
    args = parser.parse_args()

    os.environ["DB_IP"] = args.redis_ip
    os.environ["ALPHAMINI_ID"] = args.alphamini_id
    SICComponentManager(mini_component_list, client_id=args.client_id, name="Alphamini")
