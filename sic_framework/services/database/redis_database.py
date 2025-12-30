from datetime import datetime, timezone
from typing import Optional

import redis
from redis.exceptions import OutOfMemoryError, DataError, RedisError

from sic_framework import SICConfMessage, SICComponentManager, SICMessage, SICRequest, SICSuccessMessage
from sic_framework.core.component_python2 import SICComponent
from sic_framework.core.connector import SICConnector
from sic_framework.core.utils import is_sic_instance


class RedisDatabaseConf(SICConfMessage):
    """
    Configuration for setting up the connection to a persistent Redis database.

    Args:
        host: IP address of the Redis server. Default is localhost.
        port: Port of the Redis server. Default is 6380 (broker default 6379).
        password: optional password to redis server.
        username: optional username to redis server.
        socket_connect_timeout: timeout for connecting to Redis server. Default is 2 seconds.
        socket_timeout: socket timeout in seconds. Default is 2 seconds.
        decode_responses: whether to decode standard byte response from Redis server. Default is True.
        namespace: basic namespace of the redis database. Default is 'store'.
        version: version of the namespace. Default is 'v1'.
        developer_id: id of the developer user. Default is 0.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6380, db: int = 0,
                 password: Optional[str] = None, username: Optional[str] = None,
                 socket_connect_timeout: float = 2.0, socket_timeout: float = 2.0,
                 max_connections: int = 50, decode_responses: bool = True,
                 namespace: str = "store", version: str = "v1", developer_id: str | int = 0):
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


class SetUsermodelValuesRequest(SICRequest):

    def __init__(self, user_id: str | int, keyvalues: dict) -> None:
        """

        Sets a value in the user model under the specified key of the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
            keyvalues: dictionary with all the key value pairs e.g. {'key_1': 'value_1', 'key_2': 'value_2'}
        """
        super().__init__()
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
        super().__init__()
        self.user_id = user_id
        self.keys = keys


class DeleteUsermodelValuesRequest(SICRequest):

    def __init__(self, user_id: str | int, keys: list) -> None:
        """
        Message to delete values from user models based on the provided list of keys

        Args:
            user_id: the ID of the user (i.e. interactant)
            keys: list of keys of which the values need to be deleted
        """
        super().__init__()
        self.user_id = user_id
        self.keys = keys


class GetUsermodelKeysRequest(SICRequest):

    def __init__(self, user_id: str | int) -> None:
        """
        Request to inspect the existing user model keys for the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
        """
        super().__init__()
        self.user_id = user_id


class GetUsermodelRequest(SICRequest):

    def __init__(self, user_id: str | int) -> None:
        """
        Request to retrieve the whole user model for the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
        """
        super().__init__()
        self.user_id = user_id


class DeleteUserRequest(SICRequest):

    def __init__(self, user_id: str | int) -> None:
        """
        Delete user with ID user_id

        Args:
            user_id: the ID of the user (i.e. interactant)
        """
        super().__init__()
        self.user_id = user_id


class DeleteDeveloperSegmentRequest(SICRequest):

    def __init__(self, developer_id: int | str = None) -> None:
        """
        Delete the database entries belonging to the specified developer.

        When no developer_id is provided, the segment of the active developer is deleted.

        Args:
            developer_id: the ID of the developer.
        """
        super().__init__()
        self.developer_id = developer_id


class DeleteVersionSegmentRequest(SICRequest):

    def __init__(self, version: str = None) -> None:
        """
        Delete the database entries belonging to the specified version.

        When no version is provided, the segment of the active version is deleted.

        Args:
            version: the version label.
        """
        super().__init__()
        self.version = version


class DeleteNamespaceRequest(SICRequest):

    def __init__(self, namespace: str = None) -> None:
        """
        Delete the database entries belonging to the specified namespace.

        When no namespace is provided, the segment of the active namespace is deleted.

        Args:
            namespace: the namespace label.
        """
        super().__init__()
        self.namespace = namespace


class UsermodelKeyValuesMessage(SICMessage):

    def __init__(self, user_id: str | int, keyvalues: dict) -> None:
        """

        Dictionary containing the user model (or a selection thereof) of the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
            keyvalues: dictionary with all the key value pairs e.g. {'key_1': 'value_1', 'key_2': 'value_2'}
        """
        super().__init__()
        self.user_id = user_id
        self.keyvalues = keyvalues


class UsermodelKeysMessage(SICMessage):

    def __init__(self, user_id: str | int, keys: list) -> None:
        """

        List containing all the keys in the user model of the user with the specified ID

        Args:
            user_id: the ID of the user (i.e. interactant)
            keys: list containing all the user model keys.
        """
        super().__init__()
        self.user_id = user_id
        self.keys = keys


class StoreKeyspace:

    def __init__(self, namespace: str, version: str, developer_id: str | int):
        self.namespace = namespace
        self.version = version
        self.developer_id = developer_id

    def base(self) -> str:
        return f"{self.namespace}:{self.version}:dev:{self.developer_id}"

    def base_developer(self, developer_id: str | int = None) -> str:
        if developer_id:
            return f"{self.namespace}:{self.version}:dev:{developer_id}"
        else:
            return self.base()

    def base_version(self, version: str = None) -> str:
        if version:
            return f"{self.namespace}:{version}"
        return f"{self.namespace}:{self.version}"

    def base_namespace(self, namespace: str = None) -> str:
        if namespace:
            return namespace
        return self.namespace

    def user(self, user_id) -> str:
        return f"{self.base()}:user:{user_id}"

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
        return [SetUsermodelValuesRequest, GetUsermodelValuesRequest, DeleteUsermodelValuesRequest,
                GetUsermodelKeysRequest, GetUsermodelRequest, DeleteUserRequest]

    @staticmethod
    def get_output():
        return [SICSuccessMessage, UsermodelKeyValuesMessage, UsermodelKeysMessage]

    @staticmethod
    def get_conf():
        return RedisDatabaseConf()

    def on_message(self, message):
        pass
        # TODO: add possibility to handle database requests asynchronously via messages too.
        # self.output_message(self.handle_database_actions(message))

    def on_request(self, request):
        return self.handle_database_actions(request)

    def handle_database_actions(self, request):
        try:
            # USER & USER MODEL CRUD
            if is_sic_instance(request, SetUsermodelValuesRequest):
                # If new user, first create it
                redis_key_user = self.keyspace_manager.user(request.user_id)

                if not self.redis.exists(redis_key_user):
                    self.redis.hset(redis_key_user, mapping={'created_at': datetime.now(timezone.utc).isoformat()})

                # Store all key value pairs in the user model
                self.redis.hset(self.keyspace_manager.user_model(request.user_id),
                                mapping=request.keyvalues)
                return SICSuccessMessage()

            elif is_sic_instance(request, GetUsermodelValuesRequest):
                # Retrieve user model values with keys
                values = self.redis.hmget(self.keyspace_manager.user_model(request.user_id),
                                          request.keys)
                # Link values to appropriate keys before returning the results
                return UsermodelKeyValuesMessage(user_id=request.user_id,
                                                 keyvalues=dict(zip(request.keys, values)))

            elif is_sic_instance(request, GetUsermodelKeysRequest):
                keys = self.redis.hkeys(self.keyspace_manager.user_model(request.user_id))
                return UsermodelKeysMessage(user_id=request.user_id, keys=keys)

            elif is_sic_instance(request, GetUsermodelRequest):
                keyvalues = self.redis.hgetall(self.keyspace_manager.user_model(request.user_id))
                return UsermodelKeyValuesMessage(user_id=request.user_id, keyvalues=keyvalues)

            elif is_sic_instance(request, DeleteUsermodelValuesRequest):
                self.redis.hdel(self.keyspace_manager.user_model(request.user_id), *request.keys)
                return SICSuccessMessage()

            elif is_sic_instance(request, DeleteUserRequest):
                return self.delete(self.keyspace_manager.user(request.user_id))

            # DATABASE MANAGEMENT
            elif is_sic_instance(request, DeleteDeveloperSegmentRequest):
                return self.delete(self.keyspace_manager.base_developer(request.developer_id))

            elif is_sic_instance(request, DeleteVersionSegmentRequest):
                return self.delete(self.keyspace_manager.base_version(request.version))

            elif is_sic_instance(request, DeleteNamespaceRequest):
                return self.delete(self.keyspace_manager.base_namespace(request.namespace))

            else:
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

    def delete(self, keyspace):
        # Find all keys in this keyspace
        all_keys = list(self.redis.scan_iter(match=f'{keyspace}:*'))
        # Delete all entries
        self.redis.delete(*all_keys)
        return SICSuccessMessage()

    def stop(self):
        """
        Stop the RedisDatabaseComponent.
        """
        self._stopped.set()
        super().stop()


class RedisDatabase(SICConnector):
    """Connector for Redis database component"""
    component_class = RedisDatabaseComponent


def main():
    SICComponentManager([RedisDatabaseComponent], name="RedisDatabase")


if __name__ == "__main__":
    main()
