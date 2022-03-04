from redis import Redis
redis_host = 'kcloud-pp-voice-1.wzjwxg.ng.0001.apse1.cache.amazonaws.com'
r = Redis(redis_host, socket_connect_timeout=1)
r.ping()
print('redis connection successfully established "{}"' .format(redis_host))
