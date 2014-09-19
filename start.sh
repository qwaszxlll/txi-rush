#!/bin/bash

cd /home/ubuntu/txi-rush
gunicorn -w 10  --access-logfile access.log --error-logfile error.log -p gunicorn.pid -b 0.0.0.0:5001 -D app:app 
