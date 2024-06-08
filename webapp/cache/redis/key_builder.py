from conf.config import settings


def get_file_resize_cache(mem_id: str) -> str:
    return f'{settings.REDIS_SIRIUS_CACHE_PREFIX}:file_resize:{mem_id}'
