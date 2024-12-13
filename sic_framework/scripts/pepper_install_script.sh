#!/bin/bash

# export environment variables for naoqi
export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages;
export LD_LIBRARY_PATH=/opt/aldebaran/lib/naoqi;

if [ -f ~/.local/bin/virtualenv ]; then
    echo "virtualenv is installed"
else
    echo "virtualenv is not installed"
    exit 1
fi;

# create virtual environment if it doesn't exist
if [ ! -d ~/.venv_sic ]; then

    echo "virtual environment has not been initiated"
    exit 2
else
    echo "sic venv exists already";
    # activate virtual environment if it exists
    source ~/.venv_sic/bin/activate;

    cd ~/framework
    git clone https://github.com/Social-AI-VU/social-interaction-cloud.git
    cd social-interaction-cloud
    pip install .
fi;