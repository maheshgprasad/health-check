import pika
RABBIT_HOST="10.90.0.12"
RABBIT_PORT=5672
RABBIT_USERNAME="hexa"
RABBIT_PASSWORD="xAN5JsbLlMJm8kCX"

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
