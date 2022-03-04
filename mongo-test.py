import pymongo
MONGO_USER=""
MONGO_PASSWORD=""
MONGO_HOST=""
MONGO_PORT=

mongo_url="mongodb://babble:56e0af34-86b3-4775-81f1-b07ced38f812@10.90.1.86:27017/?authSource=admin"

try:
    client = pymongo.MongoClient(config.mongo_url)
    client.admin.command('ismaster')
    print("Successfully connected to mongodb")
    return True
except:
    print("Unable to connect to Mongodb")
