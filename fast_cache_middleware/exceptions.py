class FastCacheMiddlewareError(Exception):
    pass


class StorageError(FastCacheMiddlewareError):
    pass


class NotFoundError(StorageError):
    def __init__(self, key: str, message: str = "Data not found") -> None:
        self.key = key
        self.message = message
        super().__init__(f"{message}. Key: {key}.")
