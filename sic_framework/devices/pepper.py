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
from sic_framework.devices.common_naoqi.pepper_tablet import (
    NaoqiTablet,
    NaoqiTabletComponent,
)
from sic_framework.devices.naoqi_shared import *
from sic_framework.devices.device import SICLibrary

# this is where dependency binaries are downloaded to on the Pepper machine
_LIB_DIRECTORY = "/home/nao/sic_framework_2/social-interaction-cloud-main/lib"

_LIBS_TO_INSTALL = [
    SICLibrary(
        "redis",
        lib_path="/home/nao/sic_framework_2/social-interaction-cloud-main/lib/redis",
        lib_install_cmd="pip install --user redis-3.5.3-py2.py3-none-any.whl"
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
        version="1.16",
        lib_path=_LIB_DIRECTORY,
        lib_install_cmd="pip install --user numpy-1.16.6-cp27-cp27mu-manylinux1_i686.whl",
    ),
]

class Pepper(Naoqi):
    """
    Wrapper for Pepper device to easily access its components (connectors)
    """

    def __init__(self, ip, stereo_camera_conf=None, depth_camera_conf=None, **kwargs):
        super().__init__(
            ip,
            robot_type="pepper",
            venv=False,
            username="nao",
            passwords=["pepper", "nao"],
            # device path is where this script is located on the actual Pepper machine
            device_path="/home/nao/sic_framework_2/social-interaction-cloud-main/sic_framework/devices",
            **kwargs
        )

        self.configs[StereoPepperCamera] = stereo_camera_conf
        self.configs[DepthPepperCamera] = depth_camera_conf

    def check_sic_install(self):
        """
        Runs a script on Pepper to see if the sic_framework folder is there.
        """
        _, stdout, _ = self.ssh_command(
            """
                    if pip list | grep -w 'social-interaction-cloud' > /dev/null 2>&1 ; then
                        echo "SIC is installed";
                    else
                        echo "SIC is not installed";
                    fi;
                    """
        )

        output = stdout.read().decode()

        if "SIC is installed" in output:
            # this command gets the version of SIC that is currently installed on the local machine
            version_cmd = """pip list | grep 'social-interaction-cloud' | awk '{gsub(/[()]/, "", $2); print $2}'"""
            try:
                cur_version = subprocess.check_output(version_cmd, shell=True, text=True).strip()
            except subprocess.CalledProcessError as e:
                self.logger.error("Exception encountered while grabbing current SIC version:", e)

            # check to make sure the Pepper version is up-to-date (assuming the latest version of SIC is installed locally)
            _, stdout, _ = self.ssh_command(
                """
                        {version_cmd} > /home/nao/sic_framework_2/version.txt;
                        cat /home/nao/sic_framework_2/version.txt;
                        """.format(version_cmd=version_cmd)
            )

            pepper_version = stdout.read().decode()
            pepper_version = pepper_version.replace("Version: ", "")
            pepper_version = pepper_version.strip()
            self.logger.info("SIC version on Pepper: {}".format(pepper_version))
            self.logger.info("SIC local version: {}".format(cur_version))

            if pepper_version == cur_version:
                self.logger.info("SIC already installed on Pepper and versions match")
                return True
            else:
                self.logger.warning("SIC is installed on Pepper but does not match the local version! Reinstalling SIC on Pepper")
                self.logger.warning("(Check to make sure you also have the latest version of SIC installed!)")
                return False
        else:
            return False

    def sic_install(self):
        """
        1. git rid of old directories for clean install
        2. curl github repository
        3. pip install --no-deps git repo
        4. install dependencies from _LIBS_TO_INSTALL
        """
        _, stdout, stderr = self.ssh_command(
            """
                    if [ -d /home/nao/sic_framework_2 ]; then
                        rm -rf /home/nao/sic_framework_2;
                    fi;
                    
                    mkdir /home/nao/sic_framework_2;
                    cd /home/nao/sic_framework_2;
                    curl -L -o sic_repo.zip https://github.com/Social-AI-VU/social-interaction-cloud/archive/refs/heads/main.zip;
                    unzip sic_repo.zip;
                    cd /home/nao/sic_framework_2/social-interaction-cloud-main;
                    pip install --user -e . --no-deps;
                                        
                    if pip list | grep -w 'social-interaction-cloud' > /dev/null 2>&1 ; then
                        echo "SIC successfully installed"
                    fi;
                    """
        )

        if not "SIC successfully installed" in stdout.read().decode():
            raise Exception(
                "Failed to install sic. Standard error stream from install command: {}".format(
                    stderr.read().decode()
                )
            )

        self.logger.info("Installing package dependencies...")

        _, stdout_pip_freeze, _ = self.ssh_command("pip freeze")
        installed_libs = stdout_pip_freeze.readlines()

        for lib in _LIBS_TO_INSTALL:
            self.logger.info("Checking if library {} is installed...".format(lib.name))
            if not lib.check_if_installed(installed_libs):
                self.logger.info("Library {} is NOT installed, installing now...".format(lib.name))
                lib.install(self.ssh)


    @property
    def stereo_camera(self):
        return self._get_connector(StereoPepperCamera)

    @property
    def depth_camera(self):
        return self._get_connector(DepthPepperCamera)

    @property
    def tablet_display_url(self):
        return self._get_connector(NaoqiTablet)

    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis_ip", type=str, required=True, help="IP address where Redis is running"
    )
    args = parser.parse_args()

    os.environ["DB_IP"] = args.redis_ip

    pepper_components = shared_naoqi_components + [
        # NaoqiLookAtComponent,
        NaoqiTabletComponent,
        DepthPepperCameraSensor,
        StereoPepperCameraSensor,
    ]

    SICComponentManager(pepper_components)
