from unittest.mock import patch

from django.test import override_settings
from django.test.client import RequestFactory
import pytest

from cacheops import cached, cached_view
from cacheops.simple import RedisCache
from cacheops.redis import redis_client

from .utils import make_inc


def test_cached():
    get_calls = make_inc(cached(timeout=100))

    assert get_calls(1) == 1
    assert get_calls(1) == 1
    assert get_calls(2) == 2
    get_calls.invalidate(2)
    assert get_calls(2) == 3

    get_calls.key(2).delete()
    assert get_calls(2) == 4

    get_calls.key(2).set(42)
    assert get_calls(2) == 42


def test_cached_view():
    get_calls = make_inc(cached_view(timeout=100))

    factory = RequestFactory()
    r1 = factory.get('/hi')
    r2 = factory.get('/hi')
    r2.META['REMOTE_ADDR'] = '10.10.10.10'
    r3 = factory.get('/bye')

    assert get_calls(r1) == 1 # cache
    assert get_calls(r1) == 1 # hit
    assert get_calls(r2) == 1 # hit, since only url is considered
    assert get_calls(r3) == 2 # miss

    get_calls.invalidate(r1)
    assert get_calls(r1) == 3 # miss

    # Can pass uri to invalidate
    get_calls.invalidate(r1.build_absolute_uri())
    assert get_calls(r1) == 4 # miss


@pytest.mark.filterwarnings("ignore")
@override_settings(CACHEOPS_DEGRADE_ON_FAILURE=True)
def test_degrade_get():
    import redis
    from cacheops.redis import _handle_connection_failure

    # NOTE: this is quite tricky because CACHEOPS_DEGRADE_ON_FAILURE is not designed to be dynamic
    with patch('redis.Redis.get', side_effect=redis.ConnectionError), \
         patch('cacheops.simple.handle_connection_failure', _handle_connection_failure):

        # Need to recreate to use patched handle_connection_failure()
        cache = RedisCache(redis_client)
        get_calls = make_inc(cache.cached(timeout=100))

        assert get_calls(1) == 1
        assert get_calls(1) == 2  # Should miss cache and execute func again
