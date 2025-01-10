from __future__ import print_function

import argparse
import os

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.devices.naoqi_shared import *


class Nao(Naoqi):
    """
    Wrapper for NAO device to easily access its components (connectors)
    """

    def __init__(self, ip, **kwargs):
        super(Nao, self).__init__(
            ip, 
            robot_type="nao", 
            username="nao", 
            passwords="nao", 
            device_path="/data/home/nao/.venv_sic/lib/python2.7/site-packages/sic_framework/devices",
            **kwargs
        )

    def check_sic_install(self):
        """
        Runs a script on Nao to see if SIC is installed there
        """
        _, stdout, _ = self.ssh_command("""
                    # export environment variables for naoqi
                    export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages;
                    export LD_LIBRARY_PATH=/opt/aldebaran/lib/naoqi;

                    if [ ! -f ~/.local/bin/virtualenv ]; then
                        pip install --user virtualenv
                    fi;
                                        
                    # state if SIC is already installed
                    if [ -d ~/.venv_sic ]; then
                        echo "SIC already installed";    

                        # activate virtual environment if it exists
                        source ~/.venv_sic/bin/activate;

                        # upgrade the social-interaction-cloud package
                        pip install --upgrade social-interaction-cloud --no-deps         
                    fi;
                    """)
        
        output = stdout.read().decode()

        if "SIC is already installed" in output:
            return True
        else:
            return False
        

    def sic_install(self):
        """
        Runs the install script specific to the Nao
        """
        _, stdout, stderr = self.ssh_command("""
                    # export environment variables for naoqi
                    export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages;
                    export LD_LIBRARY_PATH=/opt/aldebaran/lib/naoqi;

                    echo "Creating virtual environment";
                    /home/nao/.local/bin/virtualenv ~/.venv_sic;
                    source ~/.venv_sic/bin/activate;

                    # link OpenCV to the virtualenv
                    echo "Linking OpenCV to the virtual environment";
                    ln -s /usr/lib/python2.7/site-packages/cv2.so ~/.venv_sic/lib/python2.7/site-packages/cv2.so;

                    # install required packages
                    echo "Installing SIC package";
                    pip install social-interaction-cloud --no-deps;
                    pip install Pillow PyTurboJPEG numpy redis six
                                        
                    if [ -d /data/home/nao/.venv_sic/lib/python2.7/site-packages/sic_framework]; then
                        echo "SIC successfully installed"
                    fi;
                    """)
        
        output = stdout.read().decode()

        if not "SIC successfully installed" in stdout.read().decode():
            raise Exception("Failed to install sic. Standard error stream from install command: {}".format(stderr.read().decode()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis_ip", type=str, required=True, help="IP address where Redis is running"
    )
    parser.add_argument("--redis_pass", type=str, help="The redis password")
    args = parser.parse_args()

    os.environ["DB_IP"] = args.redis_ip

    if args.redis_pass:
        os.environ["DB_PASS"] = args.redis_pass

    nao_components = shared_naoqi_components + [
        # todo,
    ]

    SICComponentManager(nao_components)
