#!/bin/bash
pip install awscli botocore --upgrade

instanceId=`curl -s http://169.254.169.254/latest/meta-data/instance-id`
localIP=`curl -s http://169.254.169.254/latest/meta-data/local-ipv4`
logDisk=`mount | grep /mnt/localstorage | tr -s " " | cut -d " " -f1 | sed -e 's/xv/s/g'`
volumeId=`/opt/mesosphere/packages/python--*/bin/aws ec2 describe-instances --region eu-west-1 --instance-ids $instanceId | jq -r ".Reservations[].Instances[].BlockDeviceMappings[] | select(.DeviceName == \"$logDisk\") | .Ebs.VolumeId"`
/opt/mesosphere/packages/python--*/bin/aws ec2 create-tags --region eu-west-1 --resources $volumeId --tags Key=slaveLogs,Value="$localIP"