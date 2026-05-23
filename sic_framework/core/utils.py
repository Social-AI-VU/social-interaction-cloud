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
    sic_ip = os.environ.get("SIC_IP") or os.environ.get("SIC_HOST_IP")
    if sic_ip:
        return sic_ip

    use_tailscale = os.environ.get("USE_TAILSCALE", "").lower() in ("1", "true", "yes")

    if use_tailscale:
        import json
        import subprocess

        ts_socket = os.environ.get("TS_SOCKET")
        cmd = ["tailscale"]
        if ts_socket:
            cmd += ["--socket", ts_socket]
        cmd += ["status", "--json"]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                ips = data.get("Self", {}).get("TailscaleIPs", [])
                if ips:
                    return ips[0]
        except (FileNotFoundError, ValueError, KeyError, subprocess.TimeoutExpired):
            pass

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
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


def str_if_bytes(data, errors="replace"):
    """
    Convert bytes to string if needed.
    
    Compatibility for the channel names between python2 and python3.
    A redis channel b'name' differs from "name".
    
    Also useful for converting Redis responses that may be bytes or other types.

    :param data: The data to convert.
    :type data: str, bytes, bytearray, or any other type
    :param errors: Error handling strategy for decoding ('replace', 'ignore', 'strict').
    :type errors: str
    :return: The converted string.
    :rtype: str
    """
    if isinstance(data, (bytes, bytearray)):
        return data.decode("utf-8", errors=errors)
    if isinstance(data, str):
        return data
    return str(data)


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


def flatten_exception_group(exc):
    """
    Return leaf exceptions from a possibly nested ExceptionGroup chain.

    If ``exc`` is not a group, returns a single-element list containing ``exc``.
    """
    if type(exc).__name__ in ("BaseExceptionGroup", "ExceptionGroup"):
        leaves = []
        for sub in exc.exceptions:
            leaves.extend(flatten_exception_group(sub))
        return leaves
    return [exc]


def format_exception_message(exc):
    """
    Format an exception (including ExceptionGroup) for human-readable logs.
    """
    leaves = flatten_exception_group(exc)
    if len(leaves) == 1:
        leaf = leaves[0]
        return "{0}: {1}".format(type(leaf).__name__, leaf)
    parts = ["{0}: {1}".format(type(e).__name__, e) for e in leaves]
    return "{0} ({1})".format(type(exc).__name__, "; ".join(parts))


def extract_google_stt_transcript(result_message):
    """
    Extract transcript text from a Google Speech-to-Text ``RecognitionResult``.

    Handles both a single streaming result (``.alternatives``) and a full
    response (``.results[0].alternatives``). Returns ``None`` when there is no
    final transcript (including an empty ``response`` dict).

    :param result_message: Value returned from ``GoogleSpeechToText.request(...)``.
    :returns: Transcript string, or ``None``.
    :rtype: str | None
    """
    if not result_message or not hasattr(result_message, "response"):
        return None

    response = result_message.response
    if isinstance(response, dict):
        # Empty dict is used when the STT stream ends without a final hypothesis.
        return None

    if hasattr(response, "alternatives") and response.alternatives:
        # Streaming recognition returns a single result object with .alternatives.
        transcript = response.alternatives[0].transcript
        return transcript if transcript else None

    if hasattr(response, "results") and response.results:
        # Batch/non-streaming responses nest hypotheses under .results[0].
        first = response.results[0]
        if hasattr(first, "alternatives") and first.alternatives:
            transcript = first.alternatives[0].transcript
            return transcript if transcript else None

    return None


def create_data_stream_id(component_endpoint, input_source, length=16):
    """
    Hashes component info into a short, random-looking string.

    Args:
        component_endpoint (str): Component identifier.
        input_source (str): Input stream name.
        length (int): Length of the resulting string (default 16).

    Returns:
        str: A base64-encoded truncated hash string.
    """
    # print("Creating data stream id for \ncomponent_name: {}\ncomponent_ip: {}\ninput_source: {}".format(component_name, component_ip, input_source))
    try:
        combined = "{component_endpoint}|{input_source}".format(component_endpoint=component_endpoint, input_source=input_source)
        sha256_hash = hashlib.sha256(combined.encode('utf-8')).digest()
        encoded = base64.urlsafe_b64encode(sha256_hash).decode('utf-8')
        # print("Data stream id created: {}".format(encoded))
    except Exception as e:
        # print("Error creating data stream id: {}".format(e))
        raise e
    return encoded[:length]


def create_component_manager_channel(component_group, component_ip):
    """
    Create a deterministic channel name for a component manager.

    This lets multiple managers run on the same host without all receiving
    every start/stop request.

    :param component_group: Shared group identifier for a component manager.
    :type component_group: str
    :param component_ip: The host IP where the manager is running.
    :type component_ip: str
    :return: Channel name scoped to one manager/component family.
    :rtype: str
    """
    return "sic:cm:{component_group}:{component_ip}".format(
        component_group=component_group, component_ip=component_ip
    )

if __name__ == "__main__":
    pass
