#!/bin/bash

if [ "`ps -aux |grep sandbox |grep -v grep | wc -l | awk '{ print $1 }'`" -eq ${1} ]
then
	exit 0
else
	exit 1
fi

