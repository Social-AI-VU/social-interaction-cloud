import argparse
import subprocess
from pathlib import Path
import os

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
        _, stdout, _ = self.ssh_command("""
                    export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages;
                    export LD_LIBRARY_PATH=/opt/aldebaran/lib/naoqi;

                    if [ -d /home/nao/sic_framework_2/social-interaction-cloud-main/sic_framework ]; then
                        echo "sic framework is installed"
                    else
                        echo "sic framework is not installed"
                    fi;
                    """)
        
        output = stdout.read().decode()

        if "is installed" in output:
            return True
        else:
            return False

    def sic_install(self):
        """
        1. check to see if directories exist, if not, make them
        2. curl github repository
        3. pip install --no-deps
        4. install dependencies
        5. if not all dependencies installed, sync .whls over and pip install
        """
        _, stdout, stderr = self.ssh_command("""
                    if [ -d /home/nao/sic_framework_2 ]; then
                        rm -rf /home/nao/sic_framework_2;
                    fi;
                    
                    mkdir /home/nao/sic_framework_2;
                    cd /home/nao/sic_framework_2;
                    curl -L -o sic_repo.zip https://github.com/Social-AI-VU/social-interaction-cloud/archive/refs/heads/main.zip;
                    unzip sic_repo.zip;
                    cd /home/nao/sic_framework_2/social-interaction-cloud-main;
                    pip install -e . --no-deps;
                                        
                    if [ -d /home/nao/sic_framework_2/social-interaction-cloud-main/sic_framework ]; then
                        echo "SIC successfully installed"
                    fi;
                    """)
        
        if not "SIC successfully installed" in stdout.read().decode():
            raise Exception("Failed to install sic. Standard error stream from install command: {}".format(stderr.read().decode()))

        print("Installing package dependencies...")

        # install dependency .whls on pepper
        _, stdout, stderr = self.ssh_command("""
                    cd /home/nao/sic_framework_2/social-interaction-cloud-main/sic_framework/devices/dep_whls;
                    pip install *.whl
                    """)
        

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
