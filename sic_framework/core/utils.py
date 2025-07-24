"""
utils.py

This module contains utility functions for the SIC framework.
"""

import binascii
import getpass
import os
import socket
import sys
import shutil
import hashlib
import base64
import six

PYTHON_VERSION_IS_2 = sys.version_info[0] < 3

MAGIC_STARTED_COMPONENT_MANAGER_TEXT = "Started component manager"


def get_ip_adress():
    """
    Get the IP address of the device.

    :return: The IP address of the device.
    :rtype: str
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(("10.254.254.254", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP

def ping_server(server, port, timeout=3):
    """
    Ping a server to check if it is reachable.

    :param server: The server to ping.
    :type server: str
    :param port: The port to ping.
    :type port: int
    :param timeout: The timeout in seconds.
    :type timeout: float
    :return: True if the server is reachable, False otherwise.
    :rtype: bool
    """
    try:
        # print("attempting to connect to device at server: {} and port: {}".format(server, port))
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server, port))
    except OSError as error:
        print("OSError when trying to connect to device: {}".format(error))
        return False
    except Exception as e:
        print("Encountered exception while trying to connect to device: {}".format(e))
    else:
        s.close()
        return True


def get_username_hostname_ip():
    """
    Get the username, hostname and IP address of the device.

    :return: The username, hostname and IP address of the device.
    :rtype: str
    """
    return getpass.getuser() + "_" + socket.gethostname() + "_" + get_ip_adress()


def ensure_binary(s, encoding="utf-8", errors="strict"):
    """
    From a future six version.
    Coerce **s** to six.binary_type.

    For Python 2:
      - `unicode` -> encoded to `str`
      - `str` -> `str`

    For Python 3:
      - `str` -> encoded to `bytes`
      - `bytes` -> `bytes`

    :param s: The string to convert.
    :type s: str
    :param encoding: The encoding to use.
    :type encoding: str
    :param errors: The error handling strategy.
    :type errors: str
    :return: The converted string.
    :rtype: str
    """
    if isinstance(s, six.binary_type):
        return s
    if isinstance(s, six.text_type):
        return s.encode(encoding, errors)
    raise TypeError("not expecting type '%s'" % type(s))


def str_if_bytes(data):
    """
    Compatibility for the channel names between python2 and python3
    a redis channel b'name' differes from "name"

    :param data: The data to convert.
    :type data: str or bytes
    :return: The converted string.
    :rtype: str
    """
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def random_hex(nbytes=8):
    """
    Generate a random hex string.

    :param nbytes: The number of bytes to generate.
    :type nbytes: int
    :return: The random hex string.
    :rtype: str
    """
    return binascii.b2a_hex(os.urandom(nbytes))


def is_sic_instance(obj, cls):
    """
    Return True if the object argument is an instance of the classinfo argument, or of a (direct, indirect,
    or virtual) subclass thereof.

    isinstance does not work when pickling object, so a looser class name check is performed.
    https://stackoverflow.com/questions/620844/why-do-i-get-unexpected-behavior-in-python-isinstance-after-pickling
    :param obj:
    :param cls:
    :return:
    """
    parents = obj.__class__.__mro__
    for parent in parents:
        if parent.__name__ == cls.__name__:
            return True

    return False


def type_equal_sic(a, b):
    """
    Check if two objects are of the same type.

    type(a) == type(b), but with support for objects transported across the network with pickle.

    :param a: The first object.
    :type a: object
    :param b: The second object.
    :type b: object
    :return:
    """
    return type(a).__name__ == type(b).__name__


def zip_directory(path):
    """
    Create a compressed zip file from the given directory path.
    
    :param path: The path to the directory to be zipped.
    :type path: str
    :return: The path to the created zip file.
    :rtype: str
    :raises: FileNotFoundError: If the path doesn't exist
    """

    # check if the path exists
    if not os.path.exists(path):
        raise FileNotFoundError("Path {path} does not exist".format(path=path))
    
    # Get the directory and name
    directory = os.path.dirname(path)
    name = os.path.basename(path)
    
    # Create base name for the zip (without .zip extension)
    base_name = os.path.join(directory, name)
    
    try:
        # make_archive automatically adds .zip extension
        zip_filepath = shutil.make_archive(base_name, 'zip', directory, name)
        return zip_filepath
            
    except Exception as e:
        raise IOError("Error while zipping: {}".format(str(e)))


def create_data_stream_id(component_id, input_source, length=16):
    """
    Hashes component info into a short, random-looking string.

    Args:
        component_id (str): Component identifier.
        input_source (str): Input stream name.
        length (int): Length of the resulting string (default 16).

    Returns:
        str: A base64-encoded truncated hash string.
    """
    # print("Creating data stream id for \ncomponent_name: {}\ncomponent_ip: {}\ninput_source: {}".format(component_name, component_ip, input_source))
    try:
        combined = "{component_id}|{input_source}".format(component_id=component_id, input_source=input_source)
        sha256_hash = hashlib.sha256(combined.encode('utf-8')).digest()
        encoded = base64.urlsafe_b64encode(sha256_hash).decode('utf-8')
        # print("Data stream id created: {}".format(encoded))
    except Exception as e:
        # print("Error creating data stream id: {}".format(e))
        raise e
    return encoded[:length]

if __name__ == "__main__":
    pass
