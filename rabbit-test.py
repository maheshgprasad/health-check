import pika
from decouple import config
RABBIT_HOST=config('RABBIT_HOST')
RABBIT_PORT=config('RABBIT_PORT')
RABBIT_USERNAME=config('RABBIT_USERNAME')
RABBIT_PASSWORD=config('RABBIT_PASSWORD')

credentials = pika.PlainCredentials(RABBIT_USERNAME, RABBIT_PASSWORD)
parameters = pika.ConnectionParameters(host=RABBIT_HOST, port=RABBIT_PORT, virtual_host='/',credentials=credentials)

try:
  connection = pika.BlockingConnection(parameters)
  if connection.is_open:
    print('rabbit-mq connection successfully established')
    connection.close()
    exit(0)
except Exception as error:
  print('Error:', error.__class__.__name__)
  exit(1)
