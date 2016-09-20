#!/bin/bash -xe

sh -xe automation/jenkins_check_yaml.sh
python automation/check_publishers_not_deleted.py
