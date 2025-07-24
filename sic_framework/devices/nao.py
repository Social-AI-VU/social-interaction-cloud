from __future__ import print_function

import argparse
import os

from sic_framework.core.component_manager_python2 import SICComponentManager
from sic_framework.devices.common_naoqi.nao_motion_streamer import (
    NaoqiMotionStreamer,
    NaoqiMotionStreamerService,
)
from sic_framework.devices.naoqi_shared import *


class Nao(Naoqi):
    """
    Wrapper for NAO device to easily access its components (connectors)
    """

    def __init__(self, ip, sic_version=None, dev_test=False, test_repo=None, **kwargs):
        """
        Initialize the Nao device wrapper.

        :param ip: The IP address of the NAO robot.
        :type ip: str
        :param sic_version: The version of the SIC framework to use. Default is None which uses the same version as your local environment.
        :type sic_version: str or None, optional
        :param dev_test: Whether to use the device in development/testing mode. Default is False.
        :type dev_test: bool, optional
        :param test_repo: Path to the test repository that you want zipped and installed on the Nao. Default is None.
        :type test_repo: str or None, optional
        """
        super(Nao, self).__init__(
            ip,
            robot_type="nao",
            venv=True,
            device_path="/data/home/nao/.venv_sic/lib/python2.7/site-packages/sic_framework/devices",
            sic_version=sic_version,
            dev_test=dev_test,
            test_device_path="/home/nao/sic_in_test/social-interaction-cloud/sic_framework/devices",
            test_repo=test_repo,
            username="nao",
            passwords="nao",
            **kwargs
        )

    def check_sic_install(self):
        """
        Runs a script on Nao to see if SIC is installed there
        """

        if self.dev_test:
            # if we are testing a development version, assume it is already installed properly
            return True

        _, stdout, _, exit_status = self.ssh_command(
            """         
                    # if there is a virtual environment, activate it
                    if [ -f ~/.venv_sic/bin/activate ]; then
                        source ~/.venv_sic/bin/activate;
                    else
                        # SIC not already installed if venv does not exist, so exit
                        exit 1;
                    fi;
                    
                    if pip list | grep -w 'social-interaction-cloud' > /dev/null 2>&1 ; then
                        echo "SIC already installed";
                        # upgrade the social-interaction-cloud package
                        pip install --upgrade social-interaction-cloud=={version} --no-deps
                    else
                        echo "SIC is not installed";
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

    def sic_install(self):
        """
        Runs the install script specific to the Nao
        """
        _, stdout, stderr, exit_status = self.ssh_command(
            """
                    if [ ! -f ~/.local/bin/virtualenv ]; then
                        pip install --user virtualenv;
                    fi;                                     
                                        
                    #  create virtual environment
                    /home/nao/.local/bin/virtualenv ~/.venv_sic;
                    source ~/.venv_sic/bin/activate;

                    # link OpenCV to the virtualenv
                    ln -s /usr/lib/python2.7/site-packages/cv2.so ~/.venv_sic/lib/python2.7/site-packages/cv2.so;

                    # install required packages
                    pip install social-interaction-cloud=={version} --no-deps;
                    pip install Pillow PyTurboJPEG numpy redis six;
                                        
                    if pip list | grep -w 'social-interaction-cloud' > /dev/null 2>&1; then
                        echo "SIC successfully installed";
                    fi;
                    """.format(
                version=self.sic_version
            )
        )

        output = stdout.read().decode()
        error = stderr.read().decode()

        if not "SIC successfully installed" in output:
            raise Exception(
                "Failed to install sic. Standard error stream from install command: {}".format(
                    error
                )
            )

    def create_test_environment(self):
        """
        Creates a test environment on the Nao

        To use test environment, you must pass in a repo to the device initialization. For example:
        - Nao(ip, dev_test=True, test_repo=PATH_TO_REPO) OR
        - Nao(ip, dev_test=True)

        If you do not pass in a repo, it will assume the repo to test is already installed in a test environment on the Nao.

        This function:
        - checks to see if test environment exists
        - if test_venv exists and no repo is passed in (self.test_repo), return True (no need to do anything)
        - if test_venv exists but a new repo has been passed in:
            1. uninstall old version of social-interaction-cloud on Nao
            2. zip the provided repo
            3. scp zip file over to nao, to 'sic_to_test' folder
            4. unzip repo and install
        - if test_venv does not exist:
            1. check to make sure a test repo has been passed in to device initialization. If not, raise RuntimeError
            2. if repo has been passed in, create a new .test_venv and install repo
        """

        def init_test_venv():
            """
            Initialize a new test virtual environment on Nao
            """
            # start with a clean slate just to be sure
            _, stdout, _, exit_status = self.ssh_command(
                """
                rm -rf ~/.test_venv;

                # create virtual environment
                /home/nao/.local/bin/virtualenv ~/.test_venv;
                source ~/.test_venv/bin/activate;

                # link OpenCV to the virtualenv
                ln -s /usr/lib/python2.7/site-packages/cv2.so ~/.test_venv/lib/python2.7/site-packages/cv2.so;

                # install required packages and perform a clean sic installation
                pip install Pillow PyTurboJPEG numpy redis six;
                """
            )

            # test to make sure the virtual environment was created
            _, stdout, _, exit_status = self.ssh_command(
                """
                source ~/.test_venv/bin/activate;
                """
            )
            if exit_status != 0:
                raise RuntimeError("Failed to create test virtual environment")

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
            Install the new repo on Nao
            """
            self.logger.info("Zipping up dev repo")
            zipped_path = utils.zip_directory(self.test_repo)

            # get the basename of the repo
            repo_name = os.path.basename(self.test_repo)

            # create the sic_in_test folder on Nao
            _, stdout, _, exit_status = self.ssh_command(
                """
                cd ~;
                rm -rf sic_in_test;
                mkdir sic_in_test;
                """
            )

            self.logger.info("Transferring zip file over to Nao")

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

            # scp transfer file over
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

            self.logger.info("Unzipping repo and installing on Nao")
            _, stdout, _, exit_status = self.ssh_command(
                """
                source ~/.test_venv/bin/activate;
                cd ~/sic_in_test;
                unzip {repo_name};
                cd {repo_name};
                pip install -e . --no-deps;
                """.format(
                    repo_name=repo_name
                )
            )

            # check to see if the repo was installed successfully
            if exit_status != 0:
                raise RuntimeError("Failed to install social-interaction-cloud")

        # check to see if test environment already exists
        _, stdout, _, exit_status = self.ssh_command(
            """
            source ~/.test_venv/bin/activate;
            """
        )

        if exit_status == 0 and not self.test_repo:
            self.logger.info(
                "Test environment already created on Nao and no new dev repo provided... skipping test_venv setup"
            )
            return True
        elif exit_status == 0 and self.test_repo:
            self.logger.info(
                "Test environment already created on Nao and new dev repo provided... uninstalling old repo and installing new one"
            )
            self.logger.warning(
                "This process may take a minute or two... Please hold tight!"
            )
            uninstall_old_repo()
            install_new_repo()
        elif exit_status == 1 and self.test_repo:
            # test environment not created, so create one
            self.logger.info(
                "Test environment not created on Nao and new dev repo provided... creating test environment and installing new repo"
            )
            self.logger.warning(
                "This process may take a minute or two... Please hold tight!"
            )
            init_test_venv()
            install_new_repo()
        elif exit_status == 1 and not self.test_repo:
            self.logger.error(
                "No test environment present on Nao and no new dev repo provided... raising RuntimeError"
            )
            raise RuntimeError("Need to provide repo to create test environment")
        else:
            self.logger.error(
                "Activating test environment on Nao resulted in unknown exit status: {}".format(
                    exit_status
                )
            )
            raise RuntimeError(
                "Unknown error occurred while creating test environment on Nao"
            )

    def motion_streaming(self, input_source=None):
        return self._get_connector(NaoqiMotionStreamer, input_source=input_source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redis_ip", type=str, required=True, help="IP address where Redis is running"
    )
    parser.add_argument(
        "--client_id", type=str, required=True, help="Client that is using this device"
    )
    parser.add_argument("--redis_pass", type=str, help="The redis password")
    args = parser.parse_args()

    os.environ["DB_IP"] = args.redis_ip

    if args.redis_pass:
        os.environ["DB_PASS"] = args.redis_pass

    nao_components = shared_naoqi_components + [NaoqiMotionStreamerService]

    SICComponentManager(nao_components, client_id=args.client_id, name="Nao")
