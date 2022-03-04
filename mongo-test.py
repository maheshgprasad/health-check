import pymongo
from decouple import config

mongo_url=config('MONGO_URL')

try:
    client = pymongo.MongoClient(mongo_url)
    client.admin.command('ismaster')
    print("mongodb connection successfully established")
except:
    print("Unable to connect to Mongodb")
