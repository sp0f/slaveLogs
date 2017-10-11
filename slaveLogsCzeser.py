#!/usr/bin/env python
# -*- coding: utf-8 -*-

import boto3
import requests

ec2 = boto3.resource('ec2')
slaveLogsTagKey="slaveLogs"

def getTag(taggedObject, tagKey):
    """get tag defined by tagKey param for collection(ec2.Instance, ec2.Image etc.)"""
    for tag in taggedObject.tags:
        if tag['Key'] == tagKey:
            #logging.debug("Found tag %s with value %s",tagKey,tag['Value'])
            return tag['Value']
   # logging.warn("Tag %s not found",tagKey)
    return None

volumes = ec2.volumes.filter(Filters=[
    {
        'Name': 'tag-key',
        'Values': [slaveLogsTagKey]
    },
    {
        'Name': 'status',
        'Values': ['available']
    }
])

print('Searching for volumes')
for volume in volumes:
    ip=getTag(volume,slaveLogsTagKey)
    print(volume.id + " will be mounted with slave ip "+ip)

response = requests.get('http://169.254.169.254/latest/meta-data/instance-id')
instance_id = response.text
print instance_id
