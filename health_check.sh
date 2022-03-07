#!/bin/bash

for i in {0..3}
do
if python3 redis-test.py | grep -q 'redis connection successfully established';
then
echo -e "\e[32m REDIS ACTIVE \e[0m"
else 
echo -e "\e[31m REDIS NOT - ACTIVE \e[0m"
sleep 30s
continue
fi

if python3 mongo-test.py | grep -q 'mongodb connection successfully established';
then
echo -e "\e[32m MONGODB ACTIVE \e[0m"
else
echo -e "\e[31m MONGODB NOT ACTIVE \e[0m"
sleep 30s
continue
fi

if python3 mysql-test.py | grep -q 'mysql connection successfully established';
then
echo -e "\e[32m MySQL-DB ACTIVE \e[0m"
else
echo -e "\e[32m MySQL-DB NOT ACTIVE \e[0m"
sleep 30s
continue
fi

if python3 rabbit-test.py | grep -q 'rabbit-mq connection successfully established';
then
echo -e "\e[32m RABBIT-MQ ACTIVE \e[0m"
else
echo -e "\e[32m RABBIT-MQ NOT ACTIVE \e[0m"
sleep 30s
continue
fi
break
done
