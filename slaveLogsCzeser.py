#!/usr/bin/env python
# -*- coding: utf-8 -*-

import boto3
import requests
import subprocess
from time import sleep

ec2 = boto3.resource('ec2')
slaveLogsTagKey="slaveLogs"
slaveLogDir="/mnt/dcos.aws/"
mountCmd = "sudo /bin/mount"

def getTag(taggedObject, tagKey):
    """get tag defined by tagKey param for collection(ec2.Instance, ec2.Image etc.)"""
    for tag in taggedObject.tags:
        if tag['Key'] == tagKey:
            #logging.debug("Found tag %s with value %s",tagKey,tag['Value'])
            return tag['Value']
   # logging.warn("Tag %s not found",tagKey)
    return None

def attachVolume(volume,instance):
    # build device id list
    devices = instance.block_device_mappings
    device_name_list=[]
    for device in devices:
        device_name_list.append(device["DeviceName"])
    # find first free device name (http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/device_naming.html)
    drive_letter="f"
    while (("/dev/sd"+drive_letter in device_name_list) or ("/dev/xvd"+drive_letter in device_name_list)):
        print "[?] Device /dev/sd"+drive_letter + " is occupied. Will try another device letter"
        drive_letter=chr(ord(drive_letter)+1)
    attach_device_name="/dev/sd"+drive_letter
    print "[*] Attaching volume "+volume.id+" to instance "+instance.id+" as "+attach_device_name
    response=instance.attach_volume(
        Device=attach_device_name,
        VolumeId=volume.id,
        DryRun=False
    )
    print "[?] Wait for attach proces to finish (volume_in_use)"
    client = boto3.client('ec2', region_name="eu-west-1")
    waiter = client.get_waiter('volume_in_use')
    waiter.wait(VolumeIds=[volume.id])
    return response, attach_device_name

def mountVolume(sysDevId,path):
    cmd = mountCmd +" "+sysDevId+" "+path
    print "[*] Mounting volume ("+cmd+")"
    sleep(3)
    try:
        stdout = subprocess.check_call(cmd.split())
    except subprocess.CalledProcessError:
        return 1
    return stdout

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
instance = ec2.Instance(local_instance_id)
print ('[?] Local instance id '+instance.id)

print('[*] Searching for abandoned slave volumes')
for volume in volumes:
    ip=getTag(volume,slaveLogsTagKey)
    _, devId = attachVolume(volume,instance)
    sysDevId="/dev/xvd"+devId[-1]
    mountPath=slaveLogDir+ip
    if (mountVolume(sysDevId,mountPath) != 0):
        print "[!] ERROR while mounting "+sysDevId+" to "+mountPath
    else:
        print "[*] "+sysDevId+" mounted to "+mountPath+" SUCCESSFULLY"
