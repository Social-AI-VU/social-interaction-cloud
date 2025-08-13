"""
sic_redis.py

A wrapper around Redis to provide a simpler interface for sending SICMessages, using two different APIs. 
The non-blocking (asynchronous) API is used for messages which are simply broadcasted and do not require a reply.
The blocking (synchronous) API is used for requests, from which a reply is expected when the action is completed.

Example Usage:
Non-blocking (asynchronous):
    ## DEVICE A
        r.register_message_handler("my_channel", do_something_fn)

    ## DEVICE B
        r.send_message("my_channel", SICMessage("abc"))


Blocking (synchronous):
    ## DEVICE A
        def do_reply(channel, request):
            return SICMessage()

        r.register_request_handler("my_channel", do_reply)

    ## DEVICE B
        reply = r.request("my_channel", NamedRequest("req_handling"), timeout=5)
    
    # here the reply is received and stored in the variable 'reply'.
"""

import atexit
import os
import threading
import time

import redis
import six
import json
from six.moves import queue

from sic_framework.core import utils
from sic_framework.core.message_python2 import SICMessage, SICRequest
from sic_framework.core.utils import is_sic_instance

class CallbackThread:
    """
    A thread that is used to listen to a channel and call a function when a message is received.

    :param function: The function to call when a message is received.
    :type function: function
    :param pubsub: The pubsub object to listen to.
    :type pubsub: redis.pubsub.PubSub
    :param thread: The thread itself
    :type thread: threading.Thread
    """

    def __init__(self, function, pubsub, thread):
        self.function = function
        self.pubsub = pubsub
        self.thread = thread


# keep track of all redis instances, so we can close them on exit
_sic_redis_instances = []


def cleanup_on_exit():
    """
    Cleanup on exit. Close all Redis connections.
    """
    from sic_framework.core import sic_logging
    logger = sic_logging.get_sic_logger("SICRedis")

    for s in _sic_redis_instances:
        s.close()

    time.sleep(0.2)
    if len([x.is_alive() for x in threading.enumerate()]) > 1:
        logger.warning("Left over threads:")
        for thread in threading.enumerate():
            if thread.is_alive() and thread.name != "SICRedisCleanup":
                logger.warning(thread.name, " is still alive")


atexit.register(cleanup_on_exit)


def get_redis_db_ip_password():
    """
    Get the Redis database IP and password from environment variables. If not set, use default values.

    :return: The Redis database IP and password.
    :rtype: tuple[str, str]
    """
    host = os.getenv("DB_IP", "127.0.0.1")
    password = os.getenv("DB_PASS", "changemeplease")
    return host, password


class SICRedis:
    """
    A custom version of Redis that provides a clear blocking and non-blocking API.

    :param parent_name: The name of the module that uses this Redis connection, for easier debugging.
    :type parent_name: str
    """

    def __init__(self, parent_name=None):

        self.stopping = False
        self._running_callbacks = []

        # hash map of data streams
        self.data_stream_map = "cache:data_streams"

        # hash map of component reservations
        self.reservation_map = "cache:reservations"

        # we assume that a password is required
        host, password = get_redis_db_ip_password()

        # Let's try to connect first without TLS / working without TLS facilitates simple use of redis-cli
        try:
            self._redis = redis.Redis(
                host=host, 
                ssl=False, 
                password=password,
                socket_timeout=1.0,  # 1 second timeout for socket operations
                socket_connect_timeout=5.0,  # 5 second timeout for connection
                retry_on_timeout=True  # Retry on timeout errors
            )
        except redis.exceptions.AuthenticationError:
            # redis is running without a password, do not supply it.
            self._redis = redis.Redis(
                host=host, 
                ssl=False,
                socket_timeout=1.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True
            )
        except redis.exceptions.ConnectionError as e:
            # Must be a connection error; so now let's try to connect with TLS
            ssl_ca_certs = os.path.join(os.path.dirname(__file__), "cert.pem")
            print(
                "TLS required. Looking for certificate here:",
                ssl_ca_certs,
                "(Source error {})".format(e),
            )
            self._redis = redis.Redis(
                host=host, 
                ssl=True, 
                ssl_ca_certs=ssl_ca_certs, 
                password=password,
                socket_timeout=1.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True
            )

        try:
            self._redis.ping()
        except redis.exceptions.ConnectionError:
            e = Exception(
                "Could not connect to redis at {} \n\n Have you started redis? Use: `redis-server conf/redis/redis.conf`".format(
                    host
                )
            )
            # six.raise_from(e, None) # unsupported on some peppers
            six.reraise(Exception, e, None)

        # To be set by any component that requires exceptions in the callback threads to be logged to somewhere
        self.parent_logger = None

        # service name (assigned to thread to help debugging)
        self.service_name = parent_name

        _sic_redis_instances.append(self)

    @staticmethod
    def parse_pubsub_message(pubsub_msg):
        """
        Convert a Redis pub/sub message to a SICMessage (sub)class.

        :param pubsub_msg: The Redis pubsub message to convert.
        :type pubsub_msg: dict
        :return: The SICMessage (sub)class.
        :rtype: SICMessage
        """
        type_, channel, data = (
            pubsub_msg["type"],
            pubsub_msg["channel"],
            pubsub_msg["data"],
        )

        if type_ == "message":
            message = SICMessage.deserialize(data)
            return message

        return None

    def register_message_handler(self, channels, callback, ignore_requests=True):
        """
        Subscribe a callback function to one or more channels, start a thread to monitor for new messages.
        
        By default, ignores SICRequests. Registering request handlers calls this function but sets ignore_requests to False.

        :param callback: a function expecting a SICMessage and a channel argument to process the messages received on `channel`
        :type callback: function
        :param channels: channel or channels to listen to.
        :type channels: str or list[str]
        :param ignore_requests: Flag to control whether the message handler should also trigger the callback if the
                                message is a SICRequest
        :type ignore_requests: bool
        :return: The CallbackThread object containing the the thread that is listening to the channel.
        """

        # convert single channel case to list of channels case
        channels = utils.str_if_bytes(channels)
        if isinstance(channels, six.text_type):
            channels = [channels]

        assert len(channels), "Must provide at least one channel"

        # ignore subscribers messages as to not trigger the callback with useless information
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)

        # unpack pubsub message to SICMessage
        def wrapped_callback(pubsub_msg):
            try:
                sic_message = self.parse_pubsub_message(pubsub_msg)

                if ignore_requests and is_sic_instance(sic_message, SICRequest):
                    return

                return callback(sic_message)
            except Exception as e:
                # Errors in a remote thread fail silently, so explicitly catch anything and log to the user.
                if self.parent_logger:
                    self.parent_logger.exception(e)
                raise e

        channels = [utils.str_if_bytes(c) for c in channels]

        pubsub.subscribe(**{c: wrapped_callback for c in channels})

        def exception_handler(e, pubsub, thread):
            # Ignore the exception if the main program is already stopping (which trigger ValueErrors)
            if not self.stopping:
                raise e

        # sleep_time is how often the thread checks if the connection is still alive (and checks the stop condition),
        # if it is 0.0 it can never time out. It can receive messages much faster, so lets be nice to the CPU with 0.1.
        if six.PY3:
            thread = pubsub.run_in_thread(
                sleep_time=0.1, daemon=False, exception_handler=exception_handler
            )
        else:
            # python2 does not support exception handler, but it's not as important to provide a clean exit on the robots
            thread = pubsub.run_in_thread(sleep_time=0.1, daemon=False)

        if self.service_name:
            thread.name = "{}_callback_thread".format(self.service_name)

        c = CallbackThread(callback, pubsub=pubsub, thread=thread)
        self._running_callbacks.append(c)

        return c

    def unregister_callback(self, callback_thread):
        """
        Unhook a callback by unsubscribing from Redis and stopping the thread. Will unregister all hooks if
        multiple hooks are created.

        :param callback_thread: The CallbackThread to unregister.
        :type callback_thread: CallbackThread
        """

        callback_thread.pubsub.unsubscribe()
        callback_thread.thread.stop()
        self._running_callbacks.remove(callback_thread)

    def send_message(self, channel, message):
        """
        Send a SICMessage on the provided channel to any subscribers.

        :param channel: The Redis pubsub channel to communicate on.
        :type channel: str
        :param message: The message to send.
        :type message: SICMessage
        :return: The number of subscribers that received the message.
        :rtype: int
        """
        assert isinstance(
            message, SICMessage
        ), "Message must inherit from SICMessage (got {})".format(type(message))

        try:
            # Let's check if we should serialize; we don't if the message is from EISComponent and needs to be sent to an
            # agent alien to SIC (who presumably does not understand Pickle objects)...
            if message.get_previous_component_name() == "EISComponent":
                return self._redis.publish(channel, message.text)
            else:
                return self._redis.publish(channel, message.serialize())
        except redis.exceptions.TimeoutError as e:
            # Log timeout but don't crash the audio stream
            if self.parent_logger:
                self.parent_logger.warning("Redis publish timeout for channel {channel}: {e}".format(channel=channel, e=e))
            return 0
        except Exception as e:
            # Log other errors but don't crash the audio stream
            if self.parent_logger:
                self.parent_logger.error("Redis publish error for channel {channel}: {e}".format(channel=channel, e=e))
            return 0

    def request(self, channel, request, timeout=5, block=True):
        """
        Send a request, and wait for the reply on the same channel. If the reply takes longer than
        `timeout` seconds to arrive, a TimeoutError is raised. If block is set to false, the reply is
        ignored and the function returns immediately.

        :param channel: The Redis pubsub channel to communicate on.
        :type channel: str
        :param request: The SICRequest
        :type request: SICRequest
        :param timeout: Timeout in seconds in case the reply takes too long.
        :type timeout: float
        :param block: If false, immediately returns None after sending the request.
        :type block: bool
        :return: the SICMessage reply
        """

        if request._request_id is None:
            raise ValueError(
                "Invalid request id for request {}".format(request.get_message_name())
            )

        # Set up a callback to listen to the same channel, where we expect the reply.
        # Once we have the reply the queue passes the data back to this thread and the
        # event signals we have received the reply. Subscribe first, as to not miss it
        # if the reply is faster than our subscription.
        done = threading.Event()
        q = queue.Queue(1)

        def await_reply(reply):
            # If not our own request but is a SICMessage with the right id, then it is the reply
            # we are waiting for
            if (
                not is_sic_instance(reply, SICRequest)
                and reply._request_id == request._request_id
            ):
                q.put(reply)
                done.set()

        if block:
            callback_thread = self.register_message_handler(channel, await_reply)

        self.send_message(channel, request)

        if not block:
            return None

        else:

            done.wait(timeout)

            if not done.is_set():
                raise TimeoutError(
                    "Waiting for reply to {} to request timed out".format(
                        request.get_message_name()
                    )
                )

            # cleanup by unsubscribing and stopping the subscriber thread
            self.unregister_callback(callback_thread)

            return q.get()

    def register_request_handler(self, channel, callback):
        """
        Register a function to listen to SICRequest's (and ignore SICMessages). Handler must return a SICMessage as a reply.
        Will block receiving new messages until the callback is finished.

        :param channel: The Redis pubsub channel to communicate on.
        :type channel: str
        :param callback: function to run upon receiving a SICRequest. Must return a SICMessage reply
        :type callback: function
        """

        def wrapped_callback(request):
            if is_sic_instance(request, SICRequest):
                reply = callback(request)

                assert not is_sic_instance(reply, SICRequest) and is_sic_instance(
                    reply, SICMessage
                ), (
                    "Request handler callback must return a SICMessage but not SICRequest, "
                    "received: {}".format(type(reply))
                )

                self._reply(channel, request, reply)

        return self.register_message_handler(
            channel, wrapped_callback, ignore_requests=False
        )

    def time(self):
        """
        Get the current time from the Redis server.

        :return: The current time in seconds since the Unix epoch.
        :rtype: tuple[int, int]
        """
        return self._redis.time()

    def close(self):
        """
        Cleanup function to stop listening to all callback channels and disconnect Redis.
        """
        self.stopping = True
        for c in self._running_callbacks:
            c.pubsub.unsubscribe()
            c.thread.stop()
        self._redis.close()

    def _reply(self, channel, request, reply):
        """
        Send a reply to a specific request. This is done by sending a SICMessage to the same channel, where
        the requesting thread/client is waiting for the reply.

        Called by request handlers.

        :param channel: The Redis pubsub channel to communicate on.
        :type channel: str
        :param request: The SICRequest
        :type request: SICRequest
        :param reply: The SICMessage reply to send back to the requesting client.
        :type reply: SICMessage
        """
        # auto-reply to the request if the request id is not set. Used for example when a service manager
        # does not want to reply to a request, so a reply is returned but its not a reply to the request
        if reply._request_id is None:
            reply._request_id = request._request_id
        self.send_message(channel, reply)

    def __del__(self):
        """
        Cleanup function to stop listening to all callback channels and disconnect Redis.
        """
        # we can no longer unregister_message_handler as python is shutting down, but we can still stop
        # any remaining threads.
        for c in self._running_callbacks:
            c.thread.stop()

    @staticmethod
    def parse_pubsub_message(pubsub_msg):
        """
        Convert a redis pub/sub message to a SICMessage (sub)class.
        :param pubsub_msg:
        :return:
        """
        type_, channel, data = (
            pubsub_msg["type"],
            pubsub_msg["channel"],
            pubsub_msg["data"],
        )

        if type_ == "message":
            message = SICMessage.deserialize(data)
            return message

        return None
    
    def get_data_stream_map(self):
        """
        Get the data stream map from redis.

        Returns a dictionary of data stream id to data stream information.
        """
        return self._redis.hgetall(self.data_stream_map)
    
    def get_reservation_map(self):
        """
        Get the reservation map from redis.

        Returns a dictionary of component id to client id.
        """
        return self._redis.hgetall(self.reservation_map)
    
    def get_data_stream(self, data_stream_id):
        """
        Get a specific data stream from redis.

        Returns the data stream as a dictionary.
        """
        # Since the data stream is stored as a string in redis, we need to convert it back to a dictionary
        raw_data_stream = self._redis.hget(self.data_stream_map, key=data_stream_id)
        return json.loads(raw_data_stream)
    
    def get_reservation(self, device_id):
        """
        Get a specific reservation from redis.

        Returns the client id that has reserved the device.
        """
        return utils.str_if_bytes(self._redis.hget(self.reservation_map, key=device_id))
    
    def set_data_stream(self, data_stream_id, data_stream_info):
        """
        Add a data stream in redis.

        :param data_stream_id: The id of the data stream
        :param data_stream_info: A dictionary containing the component id, input channel, and the client id its associated with
        """
        # Redis hashes are flat (only key-value pairs), so we need to convert the data stream to a string
        data_stream_info = {
            data_stream_id: json.dumps(data_stream_info)
        }
        return self._redis.hset(self.data_stream_map, mapping=data_stream_info)
    
    def unset_data_stream(self, data_stream_id):
        """
        Remove a data stream in redis.

        :param data_stream_id: The id of the data stream
        """
        return self._redis.hdel(self.data_stream_map, data_stream_id)
    
    def set_reservation(self, device_id, client_id):
        """
        Add a reservation for a component in redis.

        :param device_id: The id of the device
        :param client_id: The id of the client reserving the component
        :return: The number of keys set
        """
        reservation = {
            device_id: client_id
        }
        return self._redis.hset(self.reservation_map, mapping=reservation)

        
    def unset_reservation(self, device_id):
        """
        Remove a reservation for a device in redis.
        """
        return self._redis.hdel(self.reservation_map, device_id)
    
    def remove_client(self, client_id):
        """
        Remove a client's reservations and data streams from redis.

        Used if a client disconnects from the SIC server and their reservations and data streams are not removed properly.

        :param client_id: The id of the client
        """
        # delete all the reservations for the client
        reservations = self.get_reservation_map()
        for cur_device_id, cur_client_id in reservations.items():
            cur_device_id = utils.str_if_bytes(cur_device_id)
            cur_client_id = utils.str_if_bytes(cur_client_id)
            if cur_client_id == client_id:
                self.unset_reservation(cur_device_id)
        
        # delete all the data streams for the client
        data_streams = self.get_data_stream_map()
        for data_stream_id in data_streams.keys():
            data_stream_info = self.get_data_stream(data_stream_id)
            if data_stream_info["client_id"] == client_id:
                self.unset_data_stream(data_stream_id)
        
        return True
    
    def ping_client(self, client_id):
        """
        Ping a client to see if they are still connected.

        :param client_id: The id of the client
        :return: True if the client is connected, False otherwise
        """
        keyphrase="sic:logging:{}".format(client_id)
        # get list of all clients connected to the SIC server
        all_channels = self._redis.execute_command("PUBSUB", "CHANNELS")

        for channel in all_channels:
            channel_name = utils.str_if_bytes(channel)
            if keyphrase in channel_name:
                return True
        return False

if __name__ == "__main__":

    class NamedMessage(SICMessage):
        def __init__(self, name):
            self.name = name

    class NamedRequest(NamedMessage, SICRequest):
        pass

    r = SICRedis()

    def do(channel, message):
        print("do", message.name)

    # print("Message callback:")
    # r.register_message_handler("service", do, )
    # r.send_message("service", NamedMessage("abc"))
    #
    #
    # def do_reply(channel, message):
    #     print("do_reply", message.name)
    #     return NamedMessage("reply" + message.name)
    #
    #
    # print("\n\nRequest handling")
    #
    # r.register_request_handler("device", do_reply)
    # reply = r.request("device", NamedRequest("req_handling"), timeout=5)
    # print("reply:", reply.name)
    #
    # print("\n\nincorrect handler: ", )
    # try:
    #     r.register_message_handler("a", do_reply)
    #     reply = r.request("a", NamedRequest("req_incorrect_handler"), timeout=1)
    #     print("reply:", reply.name)
    # except TimeoutError as e:
    #     print("success")
    #
    # print("\n\nduplicate handler")
    # r.register_request_handler("b", do_reply)
    # r.register_message_handler("b", do)
    # reply = r.request("b", NamedRequest("req_duplicate_handler"), timeout=5)
    # print("reply:", reply.name)
    #
    # print("\n\ncallbacks")
    # for k in r._running_callbacks:
    #     print(k.function)
    #
    # print("\n\nSpeed:")
    #
    # r.register_request_handler("c", lambda *args: SICMessage())
    # start = time.time()
    # for i in range(100):
    #     reply = r.request("c", NamedRequest("req_duplicate_handler"), timeout=5)
    # print("100 request took", time.time() - start)
    #
    # start = time.time()
    # for i in range(100):
    #     r.send_message("d", SICMessage())
    # print("100 send_message took", time.time() - start)

    # print("Test callback blocking behaviour")
    #
    #
    # def do_reply_slow(channel, message):
    #     print("do_reply", message.name)
    #     time.sleep(5)
    #     return NamedMessage("reply " + message.name)
    #
    #
    # r.register_request_handler("f", do_reply_slow)
    #
    # for i in range(5):
    #     reply = r.request("f", NamedRequest(f"fast{i}"), timeout=6)
    #     print(reply.name)
    #
    # r.close()
