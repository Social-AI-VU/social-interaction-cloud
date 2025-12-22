from datetime import datetime
from typing import Optional

import redis
from redis.exceptions import ResponseError, OutOfMemoryError, DataError, RedisError

from sic_framework import SICConfMessage, SICComponentManager, SICMessage, SICRequest
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.utils import is_sic_instance


class RedisDatabaseConf(SICConfMessage):
    """
    Configuration for setting up the connection to a persistent Redis database.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6380, db: int = 0,
                 password: Optional[str] = None, username: Optional[str] = None,
                 socket_connect_timeout: float = 2.0, socket_timeout: float = 2.0,
                 max_connections: int = 50, decode_responses: bool = True,
                 namespace: str = "store", version: str = "v1", developer_id: str | int = ""):
        super(SICConfMessage, self).__init__()

        # Redis basic configuration
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.username = username
        self.socket_connect_timeout = socket_connect_timeout
        self.socket_timeout = socket_timeout
        self.max_connections = max_connections
        self.decode_responses = decode_responses

        # Redis store keyspace management
        self.namespace = namespace
        self.version = version
        self.developer_id = developer_id


class SetUsermodelValuesMessage(SICMessage):

    def __init__(self, user_id: str | int, keyvalues: dict) -> None:
        """

        Sets a value in the user model under the specified key of the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
            keyvalues: dictionary with all the key value pairs e.g. {'key_1': 'value_1', 'key_2': 'value_2'}
        """
        super(SICMessage, self).__init__()
        self.user_id = user_id
        self.keyvalues = keyvalues


class GetUsermodelValuesRequest(SICRequest):

    def __init__(self, user_id: str | int, keys: list) -> None:
        """
        Request to retrieve values from user models based on the provided list of keys

        Args:
            user_id: the ID of the user (i.e. interactant)
            keys: list of keys of which the values need to be retrieved
        """
        super(SICRequest, self).__init__()
        self.user_id = user_id
        self.keys = keys


class DeleteUsermodelValuesMessage(SICMessage):

    def __init__(self, user_id: str | int, keys: list) -> None:
        """
        Message to delete values from user models based on the provided list of keys

        Args:
            user_id: the ID of the user (i.e. interactant)
            keys: list of keys of which the values need to be deleted
        """
        super(SICMessage, self).__init__()
        self.user_id = user_id
        self.keys = keys


class GetUsermodelKeysRequest(SICRequest):

    def __init__(self, user_id: str | int) -> None:
        """
        Request to inspect the existing user model keys for the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
        """
        super(SICRequest, self).__init__()
        self.user_id = user_id


class GetUsermodelRequest(SICRequest):

    def __init__(self, user_id: str | int) -> None:
        """
        Request to retrieve the whole user model for the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
        """
        super(SICRequest, self).__init__()
        self.user_id = user_id


class DeleteUserMessage(SICMessage):

    def __init__(self, user_id: str | int) -> None:
        """
        Delete user with ID user_id

        Args:
            user_id: the ID of the user (i.e. interactant)
        """
        super(SICMessage, self).__init__()
        self.user_id = user_id


class UsermodelKeyValues(SICMessage):

    def __init__(self, user_id: str | int, keyvalues: dict) -> None:
        """

        Dictionary containing the user model (or a selection thereof) of the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
            keyvalues: dictionary with all the key value pairs e.g. {'key_1': 'value_1', 'key_2': 'value_2'}
        """
        super(SICMessage, self).__init__()
        self.user_id = user_id
        self.keyvalues = keyvalues


class UsermodelKeys(SICMessage):

    def __init__(self, user_id: str | int, keys: list) -> None:
        """

        List containing all the keys in the user model of the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
            keys: list containing all the user model keys.
        """
        super(SICMessage, self).__init__()
        self.user_id = user_id
        self.keys = keys


class StoreKeyspace:

    def __init__(self, namespace, version, developer_id):
        self.namespace = namespace
        self.version = version
        self.developer_id = developer_id

    def base(self) -> str:
        return f"{self.namespace}:{self.version}:dev_{self.developer_id}"

    def user(self, user_id) -> str:
        return f"{self.base()}:user_{user_id}"

    def user_model(self, user_id) -> str:
        return f"{self.user(user_id)}:model"


class RedisDatabaseComponent(SICComponent):
    """
    Explanation of the Redis Database Component
    TODO: write explanation
    """

    def __init__(self, *args, **kwargs):
        super(RedisDatabaseComponent, self).__init__(*args, **kwargs)

        pool = redis.ConnectionPool(
            host=self.params.host,
            port=self.params.port,
            username=self.params.username,
            password=self.params.password,
            db=self.params.db,
            decode_responses=self.params.decode_responses,
            socket_connect_timeout=self.params.socket_connect_timeout,
            socket_timeout=self.params.socket_timeout,
            max_connections=self.params.max_connections,
        )

        self.redis = redis.Redis(connection_pool=pool)

        # Fail fast: catch config/network issues early
        self.redis.ping()

        self.keyspace_manager = StoreKeyspace(namespace=self.params.namespace,
                                              version=self.params.version,
                                              developer_id=self.params.developer_id)

    @staticmethod
    def get_inputs():
        return [SetUsermodelValuesMessage, GetUsermodelValuesRequest, DeleteUsermodelValuesMessage,
                GetUsermodelKeysRequest, GetUsermodelRequest, DeleteUserMessage]

    @staticmethod
    def get_output():
        return [UsermodelKeyValues, UsermodelKeys]

    @staticmethod
    def get_conf():
        return RedisDatabaseConf()

    def on_message(self, message):
        try:
            if is_sic_instance(message, SetUsermodelValuesMessage):
                # If new user, first create it
                redis_key_user = self.keyspace_manager.user(message.user_id)
                timestamp = str(datetime.now())

                if not self.redis.exists(redis_key_user):
                    self.redis.hset(redis_key_user, mapping={'creation_data': timestamp})

                # Store all key value pairs in the user model
                self.redis.hset(self.keyspace_manager.user_model(message.user_id),
                                mapping=message.keyvalues)
            elif is_sic_instance(message, DeleteUsermodelValuesMessage):
                self.redis.hdel(self.keyspace_manager.user_model(message.user_id), message.keys)
            elif is_sic_instance(message, DeleteUserMessage):
                # Find all keys associated with this user
                all_keys = list(self.redis.scan_iter(match=f'{self.keyspace_manager.user(message.user_id)}:*'))
                # Delete all entries
                self.redis.delete(*all_keys)
            else:
                self.logger.error("Unknown message type: {}".format(type(message)))
        except OutOfMemoryError as e:
            self.logger.error("Redis store is out of memory")
            self.logger.error("Error details: {}".format(e))
        except DataError as e:
            self.logger.error("Invalid data for Redis operation:")
            self.logger.error("Error details: {}".format(e))
        except RedisError as e:
            self.logger.error("A redis error occurred:")
            self.logger.error("Error details: {}".format(e))

    def on_request(self, request):
        try:
            if is_sic_instance(request, GetUsermodelValuesRequest):
                # Retrieve user model values with keys
                values = self.redis.hmget(self.keyspace_manager.user_model(request.user_id),
                                          request.keys)
                # Link values to appropriate keys before returning the results
                return UsermodelKeyValues(user_id=request.user_id,
                                          keyvalues=zip(request.keys, values))

            if is_sic_instance(request, GetUsermodelKeysRequest):
                keys = self.redis.hkeys(self.keyspace_manager.user_model(request.user_id))
                return UsermodelKeys(user_id=request.user_id, keys=keys)

            if is_sic_instance(request, GetUsermodelRequest):
                keyvalues = self.redis.hgetall(self.keyspace_manager.user_model(request.user_id))
                return UsermodelKeyValues(user_id=request.user_id, keyvalues=keyvalues)

            self.logger.error("Unknown request type: {}".format(type(request)))
        except OutOfMemoryError as e:
            self.logger.error("Redis store is out of memory")
            self.logger.error("Error details: {}".format(e))
        except DataError as e:
            self.logger.error("Invalid data for Redis operation:")
            self.logger.error("Error details: {}".format(e))
        except RedisError as e:
            self.logger.error("A redis error occurred:")
            self.logger.error("Error details: {}".format(e))


class RedisDatabase(SICConnector):
    """Connector for Redis database component"""
    component_class = RedisDatabaseComponent


def main():
    SICComponentManager([RedisDatabaseComponent], name="RedisDatabase")


if __name__ == "__main__":
    main()
