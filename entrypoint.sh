#!/bin/bash

# Save the environment for the cron job, which starts with an empty one.
# declare -px quotes every value, unlike /etc/environment, where "#" starts
# a comment and cuts values such as CONTENT_SELECTOR=#content.
declare -px | grep -v "no_proxy" > /run/sitewatch.env
chmod 600 /run/sitewatch.env

# Start the cron service
service cron start

# Tail a log file to keep the container running
touch /var/log/cron.log
tail -f /var/log/cron.log
