# export environment variables for naoqi
export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages;
export LD_LIBRARY_PATH=/opt/aldebaran/lib/naoqi;

if [ -f ~/.local/bin/virtualenv ]; then
    echo "virtualenv is installed"
else
    echo "virtualenv is not installed. Installing now ..."
    pip install --user virtualenv
fi;

# create virtual environment if it doesn't exist
if [ ! -d ~/.venv_sic ]; then
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
else
    echo "sic venv exists already";
    # activate virtual environment if it exists
    source ~/.venv_sic/bin/activate;

    # upgrade the social-interaction-cloud package
    pip install --upgrade social-interaction-cloud --no-deps
fi;