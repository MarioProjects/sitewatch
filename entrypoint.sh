#!/bin/bash

# Export environment variables so they are available to cron
printenv | grep -v "no_proxy" >> /etc/environment

# Start the cron service
service cron start

# Tail a log file to keep the container running
touch /var/log/cron.log
tail -f /var/log/cron.log
