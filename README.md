# Deploying a Consul cluster in a VPC with Troposphere, CloudFormation and Ansible

## 1. Install Ansible on your local machine

Please refer to the Ansible docs for [how to install](http://docs.ansible.com/intro_installation.html) to your local machine.

## 2. Create the stack

Create a CloudFormation stack using `template.json` via the AWS managment console or the API. When asked for the parameters be sure to enter the appropriate availability zone letters. The zones in which you can deploy subnets into is dependent on your AWS account. The deafult is `a,b,e` because that is what my account required. Additionally, remember to enter a value key pair name so that you can ssh into the bastion and Consul servers.

## 3. Provision the bastion

The bastion will need to be provisioned in order to manage the Consul servers. First, get the bastion IP address from the stack's outputs and set the `BASTION_HOST_IP` environment variable:

```
$ export BASTION_HOST_IP=xxx.xxx.xxx.xxx
$ ansible-playbook -i hosts provision_bastion.yaml
```

## 4. Provision the Consul servers

SSH into the bastion and provision the Consul servers. Turning on SSH agent forwarding is highly recommended.

```
$ ssh-add </path/to/keypair.pem>
$ ssh ubuntu@$BASTION_HOST_IP -o ForwardAgent=yes
$ ansible-playbook -i hosts provision_consul.yaml
```

## 5. Verify the cluster

Now you'll want to SSH into one of the Consul servers and be sure that the cluster is in the desired state. The output should look like the following:

```
$ ssh 10.0.16.4
$ consul members
consul-server-10-0-16-4  10.0.16.4:8301  alive  role=consul,dc=us-east-1,vsn=1,vsn_min=1,vsn_max=1,port=8300
consul-server-10-0-48-4  10.0.48.4:8301  alive  role=consul,dc=us-east-1,vsn=1,vsn_min=1,vsn_max=1,port=8300
consul-server-10-0-32-4  10.0.32.4:8301  alive  role=consul,dc=us-east-1,vsn=1,vsn_min=1,vsn_max=1,port=8300
```

## 6. Verify DNS lookups

Check that Dnsmasq is successfully forwarding DNS queries to Consul. The output should look like the following:

```
$ dig consul-server-10-0-32-4.node.consul

; <<>> DiG 9.9.5-3-Ubuntu <<>> consul-server-10-0-32-4.node.consul
;; global options: +cmd
;; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 59853
;; flags: qr aa rd ra; QUERY: 1, ANSWER: 1, AUTHORITY: 0, ADDITIONAL: 0

;; QUESTION SECTION:
;consul-server-10-0-32-4.node.consul. IN    A

;; ANSWER SECTION:
consul-server-10-0-32-4.node.consul. 0 IN A 10.0.32.4

;; Query time: 5 msec
;; SERVER: 127.0.0.1#53(127.0.0.1)
;; WHEN: Mon Jun 09 16:55:30 UTC 2014
;; MSG SIZE  rcvd: 104
```
