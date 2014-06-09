# -*- coding: utf-8 -*-
"""
    template
    ~~~~~~~~

    Template generator
"""

from troposphere import Template, Parameter, Ref, FindInMap, Output, GetAtt, \
    Select, Join, Tags, ec2

import template_utils as utils

t = Template()

t.add_version('2010-09-09')

t.add_description(
    'A VPC stack that includes public and private subnets with a Consul '
    'cluster for DNS, service discovery and configuration management'
)

#
# Parameters
#
keyname_param = t.add_parameter(Parameter(
    'KeyName', Type='String',
    Description='Name of an existing EC2 KeyPair to enable SSH access'
))

bastion_instance_type_param = t.add_parameter(Parameter(
    'BastionInstanceType', Type='String', Default='m1.small',
    Description='Bastion EC2 instance type',
    AllowedValues=utils.EC2_INSTANCE_TYPES,
    ConstraintDescription='must be a valid EC2 instance type.'
))

consul_instance_type_param = t.add_parameter(Parameter(
    'ConsulInstanceType', Type='String', Default='m1.small',
    Description='Consul EC2 instance type',
    AllowedValues=utils.EC2_INSTANCE_TYPES,
    ConstraintDescription='must be a valid EC2 instance type.'
))

nat_instance_type_param = t.add_parameter(Parameter(
    'NATInstanceType', Type='String', Default='m1.small',
    Description='NAT Device EC2 instance type',
    AllowedValues=utils.EC2_INSTANCE_TYPES,
    ConstraintDescription='must be a valid EC2 instance type.'
))

availability_zones = t.add_parameter(Parameter(
    'AvailabilityZones', Type='CommaDelimitedList', Default='a,b,e',
    Description='A list of three availability zone letters to distribute the '
                'subnets across.'
))

#
# Mappinsg
#
t.add_mapping('AWSNATAMI', utils.get_nat_instance_mapping())
t.add_mapping('UBUNTUAMI', utils.get_bastion_instance_mapping())

#
# Resources
#
vpc = t.add_resource(ec2.VPC(
    'VPC', CidrBlock='10.0.0.0/16',
    Tags=Tags(Name=Join('', ['vpc-consul-', Ref('AWS::Region')]))
))

gateway = t.add_resource(ec2.InternetGateway(
    'InternetGateway', Tags=Tags(Name='InternetGateway')
))

gateway_attachment = t.add_resource(ec2.VPCGatewayAttachment(
    'GatewayToInternet', VpcId=Ref(vpc), InternetGatewayId=Ref(gateway)
))

public_route_table = utils.create_route_table(t, 'PublicRouteTable', vpc)

utils.create_route(
    t, 'PublicRoute', public_route_table,
    DependsOn=gateway_attachment.title,
    GatewayId=Ref(gateway)
)

public_network_acl = utils.create_network_acl(t, 'PublicNetworkAcl', vpc)

utils.create_network_acl_entry(
    t, 'InboundHTTPPublicNetworkAclEntry',
    public_network_acl, 100, (80, 80))

utils.create_network_acl_entry(
    t, 'InboundHTTPSPublicNetworkAclEntry',
    public_network_acl, 101, (443, 443))

utils.create_network_acl_entry(
    t, 'InboundSSHPublicNetworkAclEntry',
    public_network_acl, 102, (22, 22))

utils.create_network_acl_entry(
    t, 'InboundEphemeralPublicNetworkAclEntry',
    public_network_acl, 103, (1024, 65535))

utils.create_network_acl_entry(
    t, 'OutboundPublicNetworkAclEntry',
    public_network_acl, 100, (0, 65535), protocol=-1, egress=True)

nat_security_group = utils.create_security_group(
    t, 'NATSecurityGroup', 'Enables internal access to the NAT device', vpc,
    ingress=[
        ec2.SecurityGroupRule(
            IpProtocol='tcp', CidrIp=utils.WILDCARD_CIDR, FromPort=p, ToPort=p
        )
        for p in [22, 80, 443]
    ],
    egress=[
        ec2.SecurityGroupRule(
            IpProtocol='tcp', CidrIp=utils.WILDCARD_CIDR, FromPort=p, ToPort=p
        )
        for p in [80, 443]
    ]
)

consul_security_group = utils.create_security_group(
    t, 'ConsulSecurityGroup', 'Enables internal access to Consul', vpc,
    ingress=[
        ec2.SecurityGroupRule(
            IpProtocol='tcp', CidrIp=utils.WILDCARD_CIDR, FromPort=p, ToPort=p
        )
        for p in [22, 53, 8400, 8500, 8600]
    ] + [
        ec2.SecurityGroupRule(
            IpProtocol=p, CidrIp=utils.WILDCARD_CIDR, FromPort=8300, ToPort=8302
        )
        for p in ['tcp', 'udp']
    ] + [
        ec2.SecurityGroupRule(
            IpProtocol='udp', CidrIp=utils.WILDCARD_CIDR, FromPort=p, ToPort=p
        )
        for p in [53, 8400, 8500, 8600]
    ],
    egress=[
        ec2.SecurityGroupRule(
            IpProtocol='tcp', CidrIp=utils.WILDCARD_CIDR, FromPort=p, ToPort=p
        )
        for p in [53, 80, 443, 8400, 8500, 8600]
    ] + [
        ec2.SecurityGroupRule(
            IpProtocol=p, CidrIp=utils.WILDCARD_CIDR, FromPort=8300, ToPort=8302
        )
        for p in ['tcp', 'udp']
    ] + [
        ec2.SecurityGroupRule(
            IpProtocol='udp', CidrIp=utils.WILDCARD_CIDR, FromPort=p, ToPort=p
        )
        for p in [53, 8400, 8500, 8600]
    ]
)

private_network_acl = utils.create_network_acl(t, 'PrivateNetworkAcl', vpc)

utils.create_network_acl_entry(
    t, 'InboundPrivateNetworkAclEntry',
    private_network_acl, 100, (0, 65535), protocol=-1)

utils.create_network_acl_entry(
    t, 'OutBoundPrivateNetworkAclEntry',
    private_network_acl, 100, (0, 65535), protocol=-1, egress=True)

public_subnets = []
private_subnets = []

for index in range(3):

    # Public Subnet
    public_subnet = utils.create_subnet(
        t, 'PublicSubnet%s' % index, vpc,
        '10.0.%s.0/24' % index,
        Join('', [Ref('AWS::Region'), Select(index, Ref(availability_zones))]),
    )

    # Public Subnet Associations
    t.add_resource(ec2.SubnetRouteTableAssociation(
        '%sPublicRouteTableAssociation' % public_subnet.title,
        SubnetId=Ref(public_subnet),
        RouteTableId=Ref(public_route_table)
    ))

    t.add_resource(ec2.SubnetNetworkAclAssociation(
        '%sPublicSubnetNetworkAclAssociation' % public_subnet.title,
        SubnetId=Ref(public_subnet),
        NetworkAclId=Ref(public_network_acl)
    ))

    # NAT Device(s) are placed in the public subnet(s)
    name = 'NATDevice%s' % (index + 1)
    nat_device = t.add_resource(ec2.Instance(
        name,
        InstanceType=Ref(nat_instance_type_param),
        KeyName=Ref(keyname_param),
        SourceDestCheck=False,
        ImageId=FindInMap('AWSNATAMI', Ref('AWS::Region'), 'AMI'),
        NetworkInterfaces=[
            ec2.NetworkInterfaceProperty(
                Description='ENI for NAT device',
                GroupSet=[Ref(nat_security_group)],
                SubnetId=Ref(public_subnet),
                PrivateIpAddress='10.0.%s.4' % index,
                AssociatePublicIpAddress=True,
                DeviceIndex=0,
                DeleteOnTermination=True,
            )
        ],
        Tags=Tags(Name=name)
    ))

    # Private Subnet
    private_subnet = utils.create_subnet(
        t, 'PrivateSubnet%s' % index, vpc,
        '10.0.%s.0/20' % (16 + 16 * index),
        Join('', [Ref('AWS::Region'), Select(index, Ref(availability_zones))])
    )

    private_route_table = utils.create_route_table(
        t, 'PrivateRouteTable%s' % (index + 1), vpc)

    # Route all outbound traffic to the NAT
    private_route = utils.create_route(
        t, 'PrivateRoute%s' % (index + 1), private_route_table,
        InstanceId=Ref(nat_device))

    t.add_resource(ec2.SubnetRouteTableAssociation(
        '%sPrivateSubnetRouteTableAssociation' % private_subnet.title,
        SubnetId=Ref(private_subnet),
        RouteTableId=Ref(private_route_table)
    ))

    t.add_resource(ec2.SubnetNetworkAclAssociation(
        '%sPrivateSubnetNetworkAclAssociation' % private_subnet.title,
        SubnetId=Ref(private_subnet),
        NetworkAclId=Ref(private_network_acl)
    ))

    # Consul servers go in the private subnet
    name = 'ConsulHost%s' % (index + 1)
    consul_host = t.add_resource(ec2.Instance(
        name,
        InstanceType=Ref(consul_instance_type_param),
        KeyName=Ref(keyname_param),
        ImageId=FindInMap('UBUNTUAMI', Ref('AWS::Region'), 'AMI'),
        NetworkInterfaces=[
            ec2.NetworkInterfaceProperty(
                Description='ENI for Consul host',
                GroupSet=[Ref(consul_security_group)],
                SubnetId=Ref(private_subnet),
                PrivateIpAddress='10.0.%s.4' % (16 + 16 * index),
                DeviceIndex=0,
                DeleteOnTermination=True,
            )
        ],
        Tags=Tags(Name=name)
    ))

    public_subnets.append(public_subnet)
    private_subnets.append(private_subnet)

# Bastion Host.
bastion_security_group = utils.create_security_group(
    t, 'BastionSecurityGroup', 'Enables access to the bastion host', vpc,
    ingress=[
        ec2.SecurityGroupRule(IpProtocol='tcp', CidrIp=utils.WILDCARD_CIDR,
                              FromPort=22, ToPort=22)
    ],
    egress=[
        ec2.SecurityGroupRule(IpProtocol='tcp', CidrIp=s.CidrBlock,
                              FromPort=22, ToPort=22)
        for s in public_subnets + private_subnets
    ] + [
        ec2.SecurityGroupRule(IpProtocol='tcp', CidrIp=utils.WILDCARD_CIDR,
                              FromPort=p, ToPort=p)
        for p in [80, 443]
    ]
)

bastion_host = t.add_resource(ec2.Instance(
    'BastionHost',
    InstanceType=Ref(bastion_instance_type_param),
    KeyName=Ref(keyname_param),
    ImageId=FindInMap('UBUNTUAMI', Ref('AWS::Region'), 'AMI'),
    NetworkInterfaces=[
        ec2.NetworkInterfaceProperty(
            Description='ENI for bastion host',
            GroupSet=[Ref(bastion_security_group)],
            SubnetId=Ref(public_subnets[0]),
            AssociatePublicIpAddress=True,
            DeviceIndex=0,
            DeleteOnTermination=True
        )
    ],
    Tags=Tags(Name='BastionHost')
))

t.add_output([
    Output(
        'BastionIPAddress',
        Description='IP address of the bastion host',
        Value=GetAtt(bastion_host.title, 'PublicIp')
    )
])

if __name__ == '__main__':
    utils.validate_cloudformation_template(t.to_json())
    print('Template validated!')
    with open('template.json', 'w') as f:
        f.write(t.to_json())
    print('Template written to template.json')
