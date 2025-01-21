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
        print("Output from SIC installation check: {}".format(output))

        if "SIC is installed" in output:
            # this command gets the version of SIC that is currently installed on the local machine
            version_cmd = """pip list | grep 'social-interaction-cloud' | awk '{gsub(/[()]/, "", $2); print $2}'"""
            try:
                cur_version = subprocess.check_output(version_cmd, shell=True, text=True).strip()
            except subprocess.CalledProcessError as e:
                print("Exception encountered while grabbing current SIC version:", e)

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
            print("SIC version on Pepper: {}".format(pepper_version))

            if pepper_version == cur_version:
                print("SIC already installed on Pepper and versions match")
                return True
            else:
                print("SIC is installed on Pepper but does not match the local version!")
                return False
        else:
            return False

    def sic_install(self):
        """
        1. git rid of old directories for clean install
        2. curl github repository
        3. pip install --no-deps git repo
        4. install dependencies from dep_whls folder
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

        print("Installing package dependencies...")

        # install dependency .whls on pepper
        # _, stdout, stderr = self.ssh_command(
        #     """
        #             cd /home/nao/sic_framework_2/social-interaction-cloud-main/sic_framework/devices/dep_whls;
        #             pip install *.whl
        #             """
        # )


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
