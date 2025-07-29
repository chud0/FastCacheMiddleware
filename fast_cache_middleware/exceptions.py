class FastCacheMiddlewareError(Exception):
    pass


class StorageError(FastCacheMiddlewareError):
    pass


class NotFoundStorageError(StorageError):
    def __init__(self, key: str, message: str = "Data not found") -> None:
        super().__init__(f"{message}. Key: {key}.")


class TTLExpiredStorageError(StorageError):
    def __init__(self, key: str, message: str = "TTL expired") -> None:
        super().__init__(f"{message}. Key: {key}.")
