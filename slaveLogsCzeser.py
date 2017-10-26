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

def attachVolume(volume,instance):
    print ("Attach "+volume.id+" to instance "+instance.id)

    # build device id list
    devices = instance.block_device_mappings
    device_name_list=[]
    for device in devices:
        device_name_list.append(device["DeviceName"])
    # find first free device name (http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/device_naming.html)
    drive_letter="f"
    while (("/dev/sd"+drive_letter in device_name_list) or ("/dev/xvd"+drive_letter in device_name_list)):
        print "Device /dev/sd"+drive_letter + " is occupied"
        drive_letter=chr(ord(drive_letter)+1)
    attach_device_name="/dev/sd"+drive_letter
    print "Attach as "+attach_device_name
    response=instance.attach_volume(
        Device=attach_device_name,
        VolumeId=volume.id,
        DryRun=False
    )
    return response

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

response = requests.get('http://169.254.169.254/latest/meta-data/instance-id')
local_instance_id = response.text
instance = e2.Instance(local_instance_id)
print ('Local instance id '+instance.id)

print('Searching for volumes')
for volume in volumes:
    ip=getTag(volume,slaveLogsTagKey)
    attachVolume(volume,instance)

