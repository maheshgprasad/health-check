import mysql.connector
from decouple import config

mysql_host=config('DB_HOST')
mysql_port=config('DB_PORT')
mysql_username=config('DB_USERNAME')
mysql_password=config('DB_PASSWORD')
mysql_db=config('DB_NAME')

db=mysql.connector.connect(host=mysql_host, port=mysql_port, user=mysql_username, password=mysql_password, database=mysql_db)
if (db):
  print ("mysql connection successfully established")
else:
  print ("Unable to connect to MySQL")