from __future__ import print_function

import argparse
import os
import subprocess

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.devices.common_naoqi.naoqi_camera import (
    DepthPepperCamera,
    DepthPepperCameraSensor,
    StereoPepperCamera,
    StereoPepperCameraSensor,
)
from sic_framework.devices.common_naoqi.pepper_motion_streamer import (
    PepperMotionStreamer,
    PepperMotionStreamerService,
)
from sic_framework.devices.common_naoqi.pepper_tablet import (
    NaoqiTablet,
    NaoqiTabletComponent,
)
from sic_framework.devices.common_naoqi.pepper_top_tactile_sensor import (
    PepperTopTactile,
    PepperTopTactileSensor,
)
from sic_framework.devices.device import SICLibrary
from sic_framework.devices.naoqi_shared import *

# this is where dependency binaries are downloaded to on the Pepper machine
_LIB_DIRECTORY = "/home/nao/sic_framework_2/social-interaction-cloud-main/lib"

_LIBS_TO_INSTALL = [
    SICLibrary(
        "redis",
        lib_path="/home/nao/sic_framework_2/social-interaction-cloud-main/lib/redis",
        lib_install_cmd="pip install --user redis-3.5.3-py2.py3-none-any.whl",
    ),
    SICLibrary(
        "PyTurboJPEG",
        lib_path="/home/nao/sic_framework_2/social-interaction-cloud-main/lib/libturbojpeg/PyTurboJPEG-master",
        lib_install_cmd="pip install --user .",
    ),
    SICLibrary(
        "Pillow",
        download_cmd="curl -O https://files.pythonhosted.org/packages/3a/ec/82d468c17ead94734435c7801ec77069926f337b6aeae1be0a07a24bb024/Pillow-6.2.2-cp27-cp27mu-manylinux1_i686.whl",
        lib_path=_LIB_DIRECTORY,
        lib_install_cmd="pip install --user Pillow-6.2.2-cp27-cp27mu-manylinux1_i686.whl",
    ),
    SICLibrary(
        "six",
        download_cmd="curl -O https://files.pythonhosted.org/packages/b7/ce/149a00dd41f10bc29e5921b496af8b574d8413afcd5e30dfa0ed46c2cc5e/six-1.17.0-py2.py3-none-any.whl",
        lib_path=_LIB_DIRECTORY,
        lib_install_cmd="pip install --user six-1.17.0-py2.py3-none-any.whl",
    ),
    SICLibrary(
        "numpy",
        download_cmd="curl -O https://files.pythonhosted.org/packages/fd/54/aee23cfc1cdca5064f9951eefd3c5b51cff0cecb37965d4910779ef6b792/numpy-1.16.6-cp27-cp27mu-manylinux1_i686.whl",
        req_version="1.16",
        lib_path=_LIB_DIRECTORY,
        lib_install_cmd="pip install --user numpy-1.16.6-cp27-cp27mu-manylinux1_i686.whl",
    ),
]


class Pepper(Naoqi):
    """
    Wrapper for Pepper device to easily access its components (connectors)
    """

    def __init__(
        self,
        ip,
        sic_version=None,
        stereo_camera_conf=None,
        depth_camera_conf=None,
        pepper_motion_conf=None,
        **kwargs
    ):
        super().__init__(
            ip,
            robot_type="pepper",
            venv=False,
            username="nao",
            passwords=["pepper", "nao"],
            # device path is where this script is located on the actual Pepper machine
            device_path="/home/nao/sic_framework_2/social-interaction-cloud-main/sic_framework/devices",
            test_device_path="/home/nao/sic_in_test/social-interaction-cloud/sic_framework/devices",
            sic_version=sic_version,
            **kwargs
        )

        self.configs[StereoPepperCamera] = stereo_camera_conf
        self.configs[DepthPepperCamera] = depth_camera_conf
        self.configs[PepperMotionStreamer] = pepper_motion_conf

    def check_sic_install(self):
        """
        Runs a script on Pepper to see if the sic_framework folder is there.
        """

        _, stdout, _, exit_status = self.ssh_command(
            """
                pip show social-interaction-cloud;
            """
        )

        remote_stdout = stdout.read().decode()

        if exit_status != 0:
            # sic is not installed
            return False
        elif "sic_in_test" in remote_stdout:
            # test version of SIC is installed
            self.logger.info(
                "Test version of SIC is installed, uninstalling and reinstalling latest version"
            )
            return False
        else:
            self.logger.info("SIC is already installed, checking versions")

            # get the version of SIC installed on Pepper
            pepper_version = ""

            for line in remote_stdout.splitlines():
                print(line)
                if line.startswith("Version:"):
                    pepper_version = line.split(":")[1].strip()
                    break

            self.logger.info("SIC version on Pepper: {}".format(pepper_version))
            # if you don't pass sic_version, it will grab your local version
            self.logger.info("SIC local version: {}".format(self.sic_version))

            if pepper_version == self.sic_version:
                self.logger.info("SIC already installed on Pepper and versions match")
                return True
            else:
                self.logger.warning(
                    "SIC is installed on Pepper but does not match the local version or the version you passed! Reinstalling SIC on Pepper"
                )
                self.logger.warning(
                    "(Check to make sure you also have the latest version of SIC installed!)"
                )
                return False

    def sic_install(self):
        """
        Installs SIC on the Pepper

        This function:
        1. gets rid of old directories for clean install
        2. curl github repository
        3. pip install --no-deps git repo
        4. install dependencies from _LIBS_TO_INSTALL
        """
        _, stdout, stderr, exit_status = self.ssh_command(
            """
                    rm -rf /home/nao/framework;
                    if [ -d /home/nao/sic_framework_2 ]; then
                        rm -rf /home/nao/sic_framework_2;
                    fi;

                    mkdir /home/nao/sic_framework_2;
                    cd /home/nao/sic_framework_2;
                    curl -L -o sic_repo.zip https://github.com/Social-AI-VU/social-interaction-cloud/archive/refs/tags/v{version}.zip;
                    unzip sic_repo.zip;
                    mv social-interaction-cloud-{version} social-interaction-cloud-main;
                    cd social-interaction-cloud-main;
                    pip install --user -e . --no-deps;
                                        
                    if pip list | grep -w 'social-interaction-cloud' > /dev/null 2>&1 ; then
                        echo "SIC successfully installed"
                    fi;
                    """.format(
                version=self.sic_version
            )
        )

        if not "SIC successfully installed" in stdout.read().decode():
            raise Exception(
                "Failed to install sic. Standard error stream from install command: {}".format(
                    stderr.read().decode()
                )
            )

        self.logger.info("Installing package dependencies...")

        _, stdout_pip_freeze, _, exit_status = self.ssh_command("pip freeze")
        installed_libs = stdout_pip_freeze.readlines()

        for lib in _LIBS_TO_INSTALL:
            self.logger.info("Checking if library {} is installed...".format(lib.name))
            if not self.check_if_lib_installed(installed_libs, lib):
                self.logger.info(
                    "Library {} is NOT installed, installing now...".format(lib.name)
                )
                self.install_lib(lib)

    def create_test_environment(self):
        """
        Creates a test environment on the Pepper

        To use test environment, you must pass in a repo to the device initialization. For example:
        - Pepper(ip, dev_test=True, test_repo=PATH_TO_REPO) OR
        - Pepper(ip, dev_test=True)

        If you do not pass in a repo, it will assume the repo to test is already installed in a test environment on the Pepper.

        Instead of creating a virtual environment, we will just copy the repo over to the test directory
        and install from there.
        """

        def uninstall_old_repo():
            """
            Uninstall the old version of social-interaction-cloud on Alphamini
            """
            _, stdout, _, exit_status = self.ssh_command(
                """
                pip uninstall social-interaction-cloud -y
                """
            )

        def install_new_repo():
            """
            Install the new repo on Pepper
            """

            # zip up dev repo and scp over
            self.logger.info("Zipping up dev repo")
            zipped_path = utils.zip_directory(self.test_repo)
            zipped_path = self.test_repo + ".zip"
            self.logger.info("Zipped path: {}".format(zipped_path))

            # get the basename of the repo
            repo_name = os.path.basename(self.test_repo)

            self.logger.info("Removing old sic_in_test folder on Pepper")

            # create the sic_in_test folder on Nao
            _, stdout, _, exit_status = self.ssh_command(
                """
                cd ~;
                rm -rf sic_in_test;
                mkdir sic_in_test;
                """.format(
                    repo_name=repo_name
                )
            )

            self.logger.info("Transferring zip file over to Pepper")

            def progress4_callback(filename, size, sent, peername):
                print(
                    "\r({}:{}) {} progress: {:.2f}%".format(
                        peername[0],
                        peername[1],
                        filename.decode("utf-8"),
                        (float(sent) / float(size)) * 100,
                    ),
                    end="",
                )

            #  scp transfer file over
            with self.SCPClient(
                self.ssh.get_transport(), progress4=progress4_callback
            ) as scp:
                try:
                    scp.put(zipped_path, "/home/nao/sic_in_test/")
                except Exception as e:
                    self.logger.error(
                        "Error transferring zip file over to Pepper: {}".format(e)
                    )
                    raise e

            self.logger.info("Unzipping repo and installing on Pepper")

            _, stdout, _, exit_status = self.ssh_command(
                """
                cd ~/sic_in_test;
                unzip {repo_name};
                cd {repo_name};
                pip install --user -e . --no-deps;
                """.format(
                    repo_name=repo_name
                )
            )

            # check to see if the repo was installed successfully
            _, stdout, _, exit_status = self.ssh_command(
                """
                pip show social-interaction-cloud;
                """
            )

            if exit_status != 0:
                raise RuntimeError("Failed to install social-interaction-cloud")

        if self.test_repo:
            self.logger.info("Installing test repo on Pepper")
            self.logger.warning(
                "This process may take a minute or two... Please hold tight!"
            )
            uninstall_old_repo()
            install_new_repo()
        else:
            self.logger.info(
                "No test repo provided, assuming test repo is already installed"
            )
            return True

    @property
    def stereo_camera(self):
        return self._get_connector(StereoPepperCamera)

    @property
    def depth_camera(self):
        return self._get_connector(DepthPepperCamera)

    @property
    def tablet_display_url(self):
        return self._get_connector(NaoqiTablet)

    def motion_streaming(self, input_source=None):
        return self._get_connector(PepperMotionStreamer, input_source=input_source)

    @property
    def tactile_sensor(self):
        return self._get_connector(PepperTopTactile)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis_ip", type=str, required=True, help="IP address where Redis is running"
    )
    parser.add_argument(
        "--client_id", type=str, required=True, help="Client that is using this device"
    )
    args = parser.parse_args()

    os.environ["DB_IP"] = args.redis_ip

    pepper_components = shared_naoqi_components + [
        # NaoqiLookAtComponent,
        NaoqiTabletComponent,
        DepthPepperCameraSensor,
        StereoPepperCameraSensor,
        PepperMotionStreamerService,
        PepperTopTactileSensor,
    ]

    SICComponentManager(pepper_components, client_id=args.client_id, name="Pepper")
