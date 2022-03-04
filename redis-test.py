from redis import Redis
from decouple import config
redis_host=config('REDIS_HOST')
try:
    r = Redis(redis_host, socket_connect_timeout=1)
    r.ping()
    print('redis connection successfully established "{}"' .format(redis_host))
except:
    print('connection to redis un-successful')
