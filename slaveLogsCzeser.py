#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import boto3
import requests
import subprocess
from time import sleep
from sys import exit
from requests_aws_sign import AWSV4Sign
import json



ec2 = boto3.resource('ec2')
slaveLogsTagKey="slaveLogs"
slaveLogDir="/mnt/dcos.aws/"
mountCmd = "sudo /bin/mount -o nouuid"
mkdirCmd = "sudo /bin/mkdir -p"

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
    # if directory does not exist, create it (yep, i know about race condition and simply dont care;)
    if not os.path.exists(path):
        cmd = mkdirCmd+" "+path
        try:
            subprocess.check_call(cmd.split())
        except subprocess.CalledProcessError:
            print  "[!] Mount point does not exist and can't be created. Exiting."
            exit(1)
    
    cmd = mountCmd +" "+sysDevId+" "+path
    print "[*] Mounting volume ("+cmd+")"
    sleep(3)
    try:
        stdout = subprocess.check_call(cmd.split())
    except subprocess.CalledProcessError:
        print "[!] Error while mounting volume. Exiting."
        exit(1)         
    return stdout

def getAZ():
    response = requests.get('http://169.254.169.254/latest/dynamic/instance-identity/document')
    az = response.json()['availabilityZone']
    if az is None:
        print "[!] Can't determine local az. Exiting"
        exit(1)
    return az
def get_sv4_credentials():
    session = boto3.session.Session()
    credentials = session.get_credentials()
    region = session.region_name
    service = 'execute-api'

    return AWSV4Sign(credentials, region, service)

def delete_snapshot(snap_id):
    url = 'https://qbxtsbi0fl.execute-api.eu-west-1.amazonaws.com/v1/snapshot'
    headers = {'content-type': 'application/json'}
    payload = {'snap-id': snap_id }

    response = requests.delete(url, data=json.dumps(payload), headers=headers, auth=get_sv4_credentials())

    if response.status_code != requests.codes.ok:
        print("[!] Error while removing snapshot "+snap_id+": '"+response.json()['message']+"'. Please remove it manually!")




print '[*] Searching for abandoned slave volumes'

# search for tagged, unattached volumes
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

# determine local instance id
response = requests.get('http://169.254.169.254/latest/meta-data/instance-id')
local_instance_id = response.text
instance = ec2.Instance(local_instance_id)
print '[?] Local instance id '+instance.id

# determine local az
localAZ=getAZ()


# mount every abandoned volume
for volume in volumes:
    ip=getTag(volume,slaveLogsTagKey)
    
    # if volume is in different AZ: create snapshot from original volume, create new volume from snapshot in destinagion AZ
    if(localAZ != volume.availability_zone):
        print "[?] Volume "+volume.id+" in different AZ - starting miration procedure"
        snapshot=volume.create_snapshot(
            Description="Logs volume ("+volume.id+") for deleted slave "+ip,
            DryRun=False
        )
        print "[*] Creating temporary snapshot "+snapshot.id+". Waiting until completed."
        snapshot.wait_until_completed()
        # create volume from snapshot and copy src volume tag into it
        print "[*] Creating volume in destination az"
        client = boto3.client('ec2')
        result=client.create_volume(
            AvailabilityZone=localAZ,
            Encrypted=True,
            SnapshotId=snapshot.id,
            VolumeType="gp2",
            DryRun=False,
            TagSpecifications=[
                {
                    'ResourceType': 'volume',
                    'Tags': [
                        {
                            'Key': 'slaveLogs',
                            'Value': ip
                        },
                    ]
                },
            ]
        )
        new_volume=ec2.Volume(result['VolumeId'])
        print "[?] Waiting for newly created volume "+new_volume.id+" to become available"
        while new_volume.state == 'creating':
            sleep(3)
            #print "Volume state "+new_volume.state
            new_volume.reload()
        print "[*] New volume created"

        print "[*] Deleting 'slaveLogs' tag for source volume" 
        tag = ec2.Tag(volume.id, slaveLogsTagKey, ip)
        tag.delete()

        print "[*] Deleting temporary snapshot "+snapshot.id
        delete_snapshot(snapshot.id)
        volume=new_volume
        
    _, devId = attachVolume(volume,instance)
    #sysDevId="/dev/sd"+devId[-1]
    mountPath=slaveLogDir+"archive/"+ip+"/applogs"
    if (mountVolume(devId,mountPath) != 0):
        print "[!] ERROR while mounting "+sysDevId+" to "+mountPath
    else: 
        print "[*] "+devId+" mounted to "+mountPath+" SUCCESSFULLY"

if len(volumes) == 0:
    print("[*] 0 volumes found")
    exit(1)
