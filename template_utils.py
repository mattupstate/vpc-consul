# -*- coding: utf-8 -*-
"""
    template_utils
    ~~~~~~~~~~~~~~

    Template utility functions
"""

import csv
import os

import requests

import boto
from troposphere import Ref, Tags, ec2


WILDCARD_CIDR = '0.0.0.0/0'

EC2_REGIONS = [
    'us-east-1', 'us-west-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1',
    'ap-southeast-2', 'ap-northeast-1', 'sa-east-1'
]

EC2_INSTANCE_TYPES = [
    't1.micro', 'm1.small', 'm1.medium', 'm1.large', 'm1.xlarge',
    'm2.xlarge', 'm2.2xlarge', 'm2.4xlarge', 'm3.xlarge', 'm3.2xlarge',
    'c1.medium', 'c1.xlarge', 'cc1.4xlarge', 'cc2.8xlarge', 'cg1.4xlarge'
]

UBUNTU_SUITE = os.environ.get('UBUNTU_SUITE', 'trusty')
UBUNTU_AMIS_URL = 'http://cloud-images.ubuntu.com' \
                  '/query/%s/server/released.current.txt' % UBUNTU_SUITE


def get_bastion_instance_mapping():
    response = requests.get(UBUNTU_AMIS_URL)
    if response.status_code != 200:
        raise Exception('Ubuntu Image ID Data not found: ' + UBUNTU_AMIS_URL)
    csv_data = response.text.strip().split('\n')

    def get_image_id(region):
        for row in csv.reader(csv_data, delimiter='\t'):
            criteria = [
                region in row,
                'amd64' in row,
                'ebs' in row,
                'paravirtual' in row
            ]
            if all(criteria):
                return row[7]
        raise Exception('Could not find image ID for %s amd64 ebs paravirtual' % region)

    return {region: {'AMI': get_image_id(region)} for region in EC2_REGIONS}


def get_nat_instance_mapping():
    def get_image_id(region):
        c = boto.connect_ec2()
        all_images = c.get_all_images(owners='amazon', filters={'name': '*ami-vpc-nat*'})
        images = [i for i in all_images if 'beta' not in i.name]
        return sorted(images, key=lambda i: i.name, reverse=True)[0].id

    return {region: {'AMI': get_image_id(region)} for region in EC2_REGIONS}


def create_subnet(template, name, vpc, cidr_block, availability_zone):
    return template.add_resource(ec2.Subnet(
        name,
        VpcId=Ref(vpc),
        CidrBlock=cidr_block,
        AvailabilityZone=availability_zone,
        Tags=Tags(Name=name)
    ))


def create_route_table(template, name, vpc, **attrs):
    return template.add_resource(ec2.RouteTable(
        name,
        VpcId=Ref(vpc),
        Tags=Tags(Name=name),
        **attrs
    ))


def create_route(template, name, route_table, cidr_block=None, **attrs):
    cidr_block = cidr_block or WILDCARD_CIDR
    return template.add_resource(ec2.Route(
        name,
        RouteTableId=Ref(route_table),
        DestinationCidrBlock=cidr_block,
        **attrs
    ))


def create_network_acl(template, name, vpc, **attrs):
    return template.add_resource(ec2.NetworkAcl(
        name,
        VpcId=Ref(vpc),
        Tags=Tags(Name=name),
        **attrs
    ))


def create_network_acl_entry(template, name, network_acl, rule_number,
                             port_range, rule_action='allow', egress=False,
                             protocol=6, cidr_block=None, **attrs):
    cidr_block = cidr_block or WILDCARD_CIDR
    return template.add_resource(ec2.NetworkAclEntry(
        name,
        NetworkAclId=Ref(network_acl),
        RuleNumber=rule_number,
        Protocol=protocol,
        RuleAction=rule_action,
        Egress=egress,
        CidrBlock=cidr_block,
        PortRange=ec2.PortRange(From=port_range[0], To=port_range[1]),
        **attrs
    ))


def create_security_group(t, name, description, vpc, ingress, egress, **attrs):
    return t.add_resource(ec2.SecurityGroup(
        name,
        GroupDescription=description,
        VpcId=Ref(vpc),
        SecurityGroupIngress=ingress,
        SecurityGroupEgress=egress,
        Tags=Tags(Name=name),
        **attrs
    ))


def validate_cloudformation_template(template_body):
    c = boto.connect_cloudformation()
    try:
        return c.validate_template(template_body=template_body)
    except boto.exception.BotoServerError as e:
        raise Exception(e.body)
