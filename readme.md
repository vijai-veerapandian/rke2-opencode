
## RKE2
##step1 Prepare all the nodes
Following the quick steps focus on getting a close to production grade Rancher Kubernete Cluster up and running on your lab environment.

#### Set unique hostname on each node
```
sudo hostnamectl set-hostname control1   # control1/2/3, worker1/2
```
#### Disable swap (required by Kubernetes)
```
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab
```
#### Disable firewall (homelab) or open ports 6443, 9345, 2379, 2380
```
sudo ufw disable
```

##step2 Install RKE2 (control1 only)
```
curl -sfL https://get.rke2.io | sudo sh -
```
#### Create config directory and config file
```
sudo mkdir -p /etc/rancher/rke2
```
```
sudo tee /etc/rancher/rke2/config.yaml <<EOF
tls-san:
  - "192.168.2.12"          # API server VIP (MetalLB)
  - "192.168.2.58"          # control1 IP
  - "control1"
cni: none                   # Cilium installed manually next
disable-kube-proxy: true    # Cilium replaces kube-proxy
disable:
  - rke2-canal
cluster-cidr: 10.42.0.0/16
service-cidr: 10.43.0.0/16
kubelet-arg:
  - "allowed-unsafe-sysctls=net.*"
EOF
```
#### Enable and start RKE2 server
```
sudo systemctl enable rke2-server.service
```
## To avoid APR Broadcast storm on your network

Do, this only on control1 node

```
sudo mkdir -p /var/lib/rancher/rke2/server/manifests/
```
pre-stage Kube-VIP RBAC
```
sudo curl -o /var/lib/rancher/rke2/server/manifests/kube-vip-rbac.yaml https://kube-vip.io/manifests/rbac.yaml
```
Pre-stage the Kube-VIP daemoneset

Find control1 Ethernet interface detail and use it below.

```
ip address | grep -i global
```
```
sudo tee /var/lib/rancher/rke2/server/manifests/kube-vip.yaml > /dev/null << 'EOF'
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: kube-vip-ds
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: kube-vip-ds
  template:
    metadata:
      labels:
        app.kubernetes.io/name: kube-vip-ds
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: node-role.kubernetes.io/control-plane
                operator: Exists
      containers:
      - args:
        - manager
        env:
        - name: vip_arp
          value: "true"
        - name: port
          value: "6443"
        - name: vip_interface
          value: "eth0"               # <-- CHANGE THIS TO YOUR INTERFACE
        - name: vip_cidr
          value: "32"
        - name: cp_enable
          value: "true"
        - name: cp_namespace
          value: kube-system
        - name: vip_ddns
          value: "false"
        - name: svc_enable
          value: "true"
        - name: vip_leaderelection
          value: "true"
        - name: address
          value: "192.168.2.12"      # <-- CHANGE THIS TO YOUR VIP ADDRESS
        - name: prometheus_server
          value: :2112
        - name: arp_broadcast
          value: "false"              # <-- FIX: Stops continuous ARP shouting
        - name: grat_arp_period
          value: "30s"                # <-- FIX: Limits gratuitous ARP to 30s
        image: ghcr.io/kube-vip/kube-vip:v1.0.4
        imagePullPolicy: IfNotPresent
        name: kube-vip
        securityContext:
          capabilities:
            add:
            - NET_ADMIN
            - NET_RAW
            - SYS_TIME
      hostNetwork: true
      serviceAccountName: kube-vip
      tolerations:
      - effect: NoSchedule
        operator: Exists
      - effect: NoExecute
        operator: Exists
EOF
```
start the rke2-service.ser
```
sudo systemctl start rke2-server.service
```
#### Enable kubectl

```
echo 'export PATH=$PATH:/var/lib/rancher/rke2/bin' >> ~/.zshrc
echo 'export KUBECONFIG=/etc/rancher/rke2/rke2.yaml' >> ~/.zshrc
source ~/.zshrc
```
#### Enable ubuntu user to do kubectl without sudo
```
mkdir -p ~/.kube
sudo cp /etc/rancher/rke2/rke2.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
# Then update KUBECONFIG to point to your user copy
echo 'export KUBECONFIG=~/.kube/config' >> ~/.zshrc
source ~/.zshrc
```

#### Verify kubectl works
```
kubectl version --client
```
output
```
ubuntu@control1:~$ sudo systemctl status rke2-server.service
● rke2-server.service - Rancher Kubernetes Engine v2 (server)
     Loaded: loaded (/usr/local/lib/systemd/system/rke2-server.service; enabled; vendor preset: enabled)
     Active: active (running) since Sun 2026-03-29 04:09:01 UTC; 3h 44min ago
       Docs: https://github.com/rancher/rke2#readme
    Process: 245597 ExecCondition=/bin/sh -c if systemctl is-active --quiet rke2-agent.service; then echo "Error: rke2-agent is running!"; exit 1; fi (code=exited, status=0/SUCCESS)
    Process: 245599 ExecStartPre=/sbin/modprobe br_netfilter (code=exited, status=0/SUCCESS)
    Process: 245600 ExecStartPre=/sbin/modprobe overlay (code=exited, status=0/SUCCESS)
   Main PID: 245601 (rke2)
      Tasks: 124
     Memory: 3.0G
        CPU: 17min 6.379s
     CGroup: /system.slice/rke2-server.service
```

#### Follow logs until you see "Node Registered" (~2 min)
```
sudo journalctl -u rke2-server -f
```

## Get cluster token and setup kubectl 

#### Get the node token (save this — needed for all other nodes)
```
sudo cat /var/lib/rancher/rke2/server/node-token
```
#### Setup kubectl
```
mkdir -p ~/.kube
sudo cp /etc/rancher/rke2/rke2.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
```
#### Add rke2 binaries to PATH in .zshrc
```
echo 'export PATH=$PATH:/var/lib/rancher/rke2/bin' >> ~/.zshrc
echo 'export KUBECONFIG=~/.kube/config' >> ~/.zshrc
source ~/.zshrc
```
#### Node shows NotReady — that is expected (CNI not installed yet)
```
kubectl get nodes
```
## Join the master control node

#### Install RKE2 on the node
```
curl -sfL https://get.rke2.io | sudo sh -
```
```
ubuntu@worker2:~$ curl -sfL https://get.rke2.io | sudo sh -
[sudo] password for ubuntu: 
[INFO]  finding release for channel stable
[INFO]  using v1.34.5+rke2r1 as release
[INFO]  downloading checksums at https://github.com/rancher/rke2/releases/download/v1.34.5%2Brke2r1/sha256sum-amd64.txt
[INFO]  downloading tarball at https://github.com/rancher/rke2/releases/download/v1.34.5%2Brke2r1/rke2.linux-amd64.tar.gz
[INFO]  verifying tarball
[INFO]  unpacking tarball file to /usr/local
```
#### Create config file (same for control2, control3, worker1, worker2)
```
sudo mkdir -p /etc/rancher/rke2
sudo tee /etc/rancher/rke2/config.yaml <<EOF
server: https://192.168.2.58:9345
token: <paste-token-here>
tls-san:
   - "192.168.2.12"
cni: none
disable-kube-proxy: true
disable:
  - rke2-canal
kubelet-arg:
  - "allowed-unsafe-sysctls=net.*"
EOF
```
#### For control2 and control3: join as server
```
sudo systemctl enable rke2-server.service
sudo systemctl start rke2-server.service
```

#### For worker1 and worker2: join as agent instead
```
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" sudo sh -
```
```
sudo systemctl enable rke2-agent.service
sudo systemctl start rke2-agent.service
```
## Reference output
```
ubuntu@worker2:~$ curl -sfL https://get.rke2.io | sudo sh -
[INFO]  finding release for channel stable
[INFO]  using v1.34.5+rke2r1 as release
[INFO]  downloading checksums at https://github.com/rancher/rke2/releases/download/v1.34.5%2Brke2r1/sha256sum-amd64.txt
[INFO]  downloading tarball at https://github.com/rancher/rke2/releases/download/v1.34.5%2Brke2r1/rke2.linux-amd64.tar.gz
[INFO]  verifying tarball
[INFO]  unpacking tarball file to /usr/local
ubuntu@worker2:~$ 
ubuntu@worker2:~$ sudo mkdir -p /etc/rancher/rke2
ubuntu@worker2:~$ sudo tee /etc/rancher/rke2/config.yaml <<EOF
> server: https://192.168.2.58:9345
> token: <paste-token-here>
> cni: none
> disable-kube-proxy: true
> kubelet-arg:
>   - "allowed-unsafe-sysctls=net.*"
> EOF
server: https://192.168.2.58:9345
token: <paste-token-here>
ubuntu@worker2:~$ curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" sudo sh -
[INFO]  finding release for channel stable
[INFO]  using v1.34.5+rke2r1 as release
[INFO]  downloading checksums at https://github.com/rancher/rke2/releases/download/v1.34.5%2Brke2r1/sha256sum-amd64.txt
[INFO]  downloading tarball at https://github.com/rancher/rke2/releases/download/v1.34.5%2Brke2r1/rke2.linux-amd64.tar.gz
[INFO]  verifying tarball
[INFO]  unpacking tarball file to /usr/local
```
Restart the rke2-agent on the worker nodes 
```
ubuntu@worker2:~$ sydo systemctl enable rke2-agent.service
-bash: sydo: command not found
ubuntu@worker2:~$ sudo systemctl enable rke2-agent.service
ubuntu@worker2:~$ sudo systemctl start rke2-agent.service
ubuntu@worker2:~$ sudo systemctl status rke2-agent.service
● rke2-agent.service - Rancher Kubernetes Engine v2 (agent)
     Loaded: loaded (/usr/local/lib/systemd/system/rke2-agent.service; enabled; preset: enabled)
     Active: active (running) since Sun 2026-03-29 08:24:25 UTC; 39s ago
       Docs: https://github.com/rancher/rke2#readme
   Main PID: 8385 (rke2)
      Tasks: 46
     Memory: 1.6G (peak: 1.6G)
        CPU: 22.875s
     CGroup: /system.slice/rke2-agent.service
```
Verify the nodes status
```
kubectl get nodes
```
## Install Cilium

control1

#### Install Helm
```
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```
#### Add Cilium repo
```
helm repo add cilium https://helm.cilium.io/ && helm repo update
```
#### Install Gateway API CRDs (required before Cilium)
```
GWAPI=https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.1/config/crd/standard
kubectl apply -f $GWAPI/gateway.networking.k8s.io_gatewayclasses.yaml
kubectl apply -f $GWAPI/gateway.networking.k8s.io_gateways.yaml
kubectl apply -f $GWAPI/gateway.networking.k8s.io_httproutes.yaml
```
#### Install Cilium
```
helm install cilium cilium/cilium \
  --namespace kube-system \
  --set kubeProxyReplacement=true \
  --set k8sServiceHost=192.168.2.58 \
  --set k8sServicePort=6443 \
  --set gatewayAPI.enabled=true \
  --set hubble.relay.enabled=true \
  --set hubble.ui.enabled=true \
  --set cgroup.autoMount.enabled=false \
  --set cgroup.hostRoot=/sys/fs/cgroup \
  --set cni.binPath=/opt/cni/bin \
  --set cni.confPath=/etc/cni/net.d \
  --set cni.exclusive=false \
  --set sysctlfix.enabled=false \
  --set securityContext.privileged=true
  --set hostFirewall.enabled=false
  --set hostPort.enabled=true
```
#### All nodes should now go Ready
```
kubectl get nodes
```
#### Reference output on Cilium
```
ubuntu@control1:~$ curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100 11929  100 11929    0     0   150k      0 --:--:-- --:--:-- --:--:--  151k
[WARNING] Could not find git. It is required for plugin installation.
Helm v3.20.1 is already latest
ubuntu@control1:~$ 
ubuntu@control1:~$ helm repo add cilium https://helm.cilium.io/ && helm repo update
"cilium" has been added to your repositories
Hang tight while we grab the latest from your chart repositories...
...Successfully got an update from the "cilium" chart repository
Update Complete. ⎈Happy Helming!⎈
```
```
ubuntu@control1:~$ 
ubuntu@control1:~$ GWAPI=https://raw.githubusercontent.com/kubernetes-sigs/gateway-api/v1.2.1/config/crd/standard
ubuntu@control1:~$ 
ubuntu@control1:~$ kubectl apply -f $GWAPI/gateway.networking.k8s.io_gatewayclasses.yaml
customresourcedefinition.apiextensions.k8s.io/gatewayclasses.gateway.networking.k8s.io created
ubuntu@control1:~$ kubectl apply -f $GWAPI/gateway.networking.k8s.io_gateways.yaml
customresourcedefinition.apiextensions.k8s.io/gateways.gateway.networking.k8s.io created
customresourcedefinition.apiextensions.k8s.io/gateways.gateway.networking.k8s.io configured
ubuntu@control1:~$ kubectl apply -f $GWAPI/gateway.networking.k8s.io_httproutes.yaml
customresourcedefinition.apiextensions.k8s.io/httproutes.gateway.networking.k8s.io created
```
```
ubuntu@control1:~$ helm install cilium cilium/cilium \
  --namespace kube-system \
  --set kubeProxyReplacement=true \
  --set k8sServiceHost=192.168.2.58 \
  --set k8sServicePort=6443 \
  --set gatewayAPI.enabled=true \
  --set hubble.relay.enabled=true \
  --set hubble.ui.enabled=true \
  --set cgroup.autoMount.enabled=false \
  --set cgroup.hostRoot=/sys/fs/cgroup \
  --set cni.binPath=/opt/cni/bin \
  --set cni.confPath=/etc/cni/net.d \
  --set cni.exclusive=false \
  --set sysctlfix.enabled=false \
  --set securityContext.privileged=true
NAME: cilium
LAST DEPLOYED: Sun Mar 29 12:21:47 2026
NAMESPACE: kube-system
STATUS: deployed
REVISION: 1
TEST SUITE: None
NOTES:
You have successfully installed Cilium with Hubble Relay and Hubble UI.

Your release version is 1.19.2.

For any further help, visit https://docs.cilium.io/en/v1.19/gettinghelp
ubuntu@control1:~$ 
```
# All nodes should now go Ready
```
kubectl get nodes
```
```
ubuntu@control1:~$ kubectl get nodes 
NAME       STATUS   ROLES                AGE     VERSION
control1   Ready    control-plane,etcd   8h      v1.34.5+rke2r1
control2   Ready    control-plane,etcd   8h      v1.34.5+rke2r1
control3   Ready    control-plane,etcd   8h      v1.34.5+rke2r1
worker1    Ready    <none>               5h20m   v1.34.5+rke2r1
worker2    Ready    <none>               4h16m   v1.34.5+rke2r1
```

## Install MetalLB (L2)

helm repo add metallb https://metallb.github.io/metallb && helm repo update

helm install metallb metallb/metallb --namespace metallb-system --create-namespace

kubectl get pods -n metallb-system -w 

Configure an IP address pool and L2 advertisement

```
kubectl apply -f - <<EOF
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: homelab-pool
  namespace: metallb-system
spec:
  addresses:
  - 192.168.2.240-192.168.2.249
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: homelab-l2
  namespace: metallb-system
spec:
  ipAddressPools:
  - homelab-pool
EOF
```
output:
ipaddresspool.metallb.io/homelab-pool created
l2advertisement.metallb.io/homelab-l2 created

verify installation 
```
ubuntu@control1:~$ kubectl get pods -n metallb-system -w
NAME                                  READY   STATUS    RESTARTS   AGE
metallb-controller-765c495b75-g958q   1/1     Running   0          38m
metallb-speaker-8k6bp                 4/4     Running   0          38m
metallb-speaker-cw4k6                 4/4     Running   0          38m
metallb-speaker-d7f6t                 4/4     Running   0          38m
metallb-speaker-mff5w                 4/4     Running   0          38m
metallb-speaker-wzp5n                 4/4     Running   0          38m
```

```
ubuntu@control1:~$ kubectl get ipaddresspool -n metallb-system
NAME           AUTO ASSIGN   AVOID BUGGY IPS   ADDRESSES
homelab-pool   true          false             ["192.168.2.240-192.168.2.249"]
```

## Local Path Provisioner
```
kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml
```
Make it the default storageclass:

```
kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

output:
```
ubuntu@control1:~$ kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.30/deploy/local-path-storage.yaml
namespace/local-path-storage created
serviceaccount/local-path-provisioner-service-account created
role.rbac.authorization.k8s.io/local-path-provisioner-role created
clusterrole.rbac.authorization.k8s.io/local-path-provisioner-role created
rolebinding.rbac.authorization.k8s.io/local-path-provisioner-bind created
clusterrolebinding.rbac.authorization.k8s.io/local-path-provisioner-bind created
deployment.apps/local-path-provisioner created
storageclass.storage.k8s.io/local-path created
configmap/local-path-config created
ubuntu@control1:~$ 
ubuntu@control1:~$ kubectl patch storageclass local-path -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
storageclass.storage.k8s.io/local-path patched
```
```
ubuntu@control1:~$ kubectl get storageclass
NAME                   PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
local-path (default)   rancher.io/local-path   Delete          WaitForFirstConsumer   false                  22s
ubuntu@control1:~$ 
```
## ArgoCD

```
kubectl create ns argocd 
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```
```
kubectl get pods -n argocd -w
```

Expose ArgoCD UI via LoadBalancer(using your MetalLB)

```
kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "LoadBalancer"}}'
```
```
kubectl get svc argocd-server -n argocd
```
Get the initial admin password:

```
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d && echo
```
and default user name is admin

output:


```
ubuntu@control1:~$ kubectl get pods -n argocd -w
NAME                                               READY   STATUS    RESTARTS   AGE
argocd-application-controller-0                    1/1     Running   0          53s
argocd-applicationset-controller-cf6df4d44-cmqw6   1/1     Running   0          53s
argocd-dex-server-694c74cbb8-xc85h                 1/1     Running   0          53s
argocd-notifications-controller-67dd6d74b5-bgm4c   1/1     Running   0          53s
argocd-redis-85b9d55dc4-lcjfn                      1/1     Running   0          53s
argocd-repo-server-6fd5c47689-g9hgp                1/1     Running   0          53s
argocd-server-79fdfd7f5b-nxdr2                     1/1     Running   0          53s

ubuntu@control1:~kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "LoadBalancer"}}'}'
service/argocd-server patched
```
```
ubuntu@control1:~$ kubectl get svc argocd-server -n argocd
NAME            TYPE           CLUSTER-IP     EXTERNAL-IP     PORT(S)                      AGE
argocd-server   LoadBalancer   10.43.89.130   192.168.2.240   80:30936/TCP,443:30861/TCP   2m37s
ubuntu@control1:~$ 
```

## Ollama

```
helm repo add otwld https://helm.otwld.com/
helm repo update
```

Install
```
helm install ollama otwld/ollama \
  --namespace ollama \
  --create-namespace \
  --set ollama.gpu.enabled=false \
  --set persistentVolume.enabled=true \
  --set persistentVolume.size=20Gi \
  --set ollama.models.pull[0]=qwen2.5-coder:3b \
  --set ollama.models.run[0]=qwen2.5-coder:3b \
  --set service.type=LoadBalancer \
  --set resources.requests.memory=4Gi \
  --set resources.requests.cpu=2 \
  --set resources.limits.memory=6Gi \
  --set resources.limits.cpu=4
```
```
kubectl get pods -n ollama -w 
```
```
kubectl get svc -n ollama
```
```
curl http://<External-IP>:11434/api/tags
```
output:

```
ubuntu@control1:~$ helm install ollama otwld/ollama \
  --namespace ollama \
  --create-namespace \
  --set ollama.gpu.enabled=false \
  --set persistentVolume.enabled=true \
  --set persistentVolume.size=20Gi \
  --set ollama.models.pull[0]=qwen2.5-coder:3b \
  --set ollama.models.run[0]=qwen2.5-coder:3b \
  --set service.type=LoadBalancer \
  --set resources.requests.memory=4Gi \
  --set resources.requests.cpu=2 \
  --set resources.limits.memory=6Gi \
  --set resources.limits.cpu=4
NAME: ollama
LAST DEPLOYED: Sun Mar 29 17:35:41 2026
NAMESPACE: ollama
STATUS: deployed
REVISION: 1
NOTES:
1. Get the application URL by running these commands:
     NOTE: It may take a few minutes for the LoadBalancer IP to be available.
           You can watch the status of by running 'kubectl get --namespace ollama svc -w ollama'
  export SERVICE_IP=$(kubectl get svc --namespace ollama ollama --template "{{ range (index .status.loadBalancer.ingress 0) }}{{.}}{{ end }}")
  echo http://$SERVICE_IP:11434
ubuntu@control1:~$ kubectl get --namespace ollama svc -w ollama
NAME     TYPE           CLUSTER-IP     EXTERNAL-IP     PORT(S)           AGE
ollama   LoadBalancer   10.43.136.99   192.168.2.241   11434:30687/TCP   32s
^Cubuntu@control1:~$ kubectl get svc -n ollama
NAME     TYPE           CLUSTER-IP     EXTERNAL-IP     PORT(S)           AGE
ollama   LoadBalancer   10.43.136.99   192.168.2.241   11434:30687/TCP   3m36s
```

## Set the context window

Get the ollama service IP:

```
kubectl get svc -n ollama
```

Increase the context window
```
OLLAMA_POD=$(kubectl get pod -n ollama -l app.kubernetes.io/name=ollama -o jsonpath='{.items[0].metadata.name}')
kubectl exec -it $OLLAMA_POD -n ollama -- ollama run qwen2.5-coder:3b
```

Once inside the Ollama prompt:
```
/set parameter num_ctx 16384
/save qwen2.5-coder:3b-16k
/bye
```

## Install opencode on target machine:

```
curl -fsSL https://opencode.ai/install | bash
```
Creating the OpenCode config with External Ollama IP 

```
mkdir -p ~/.config/opencode
```
```
vim > ~/.config/opencode/opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama",
      "options": {
        "baseURL": "http://<OLLAMA_IP>:11434/v1"
      },
      "models": {
        "qwen2.5-coder:3b-16k": {
          "name": "Qwen 2.5 Coder 3B (16k context)",
          "tools": true
        }
      }
    }
  }
}
```

cd /directory
opencode

/connect
/models

## Admin machine set kubectl to manage the Cluster 
Install kubectl

```
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
```
```
chmod +x kubectl
sudo mv kubectl /usr/local/bin
```
verify
```
kubectl version --client
```
In control1
```
sudo cp /etc/rancher/rke2/rke2.yaml ~/rke2.yaml
sudo chown ubuntu:ubuntu ~/rke2.yaml 
```
In Admin machine 
```
mkdir ~/.kube 
scp ubuntu@control1:~/rke2.yaml ~/.kube/config
```

In the config file change the server: https://172.0.0.1:6443 to KUBE-VIP

Verify
```
kubectl get nodes
kubectl cluster-INFO
```

## Set Kube-VIP (like HA-proxy for control nodes but through Kube-VIP)

set the variables 
```
export VIP=192.168.2.12
export INTERFACE=$(IP -4 route ls | grep default | grep -Po '(?<=dev )(\S+)')
export KVVERSION="v0.8.0"
```

Pull the RBAC rules
```
curl -s https://kube-vip.io/manifests/rbac.yaml | sudo tee /var/lib/rancher/rke2/server/manifests/kube-vip-rbac.yaml > /dev/null 
```
Generate the Daemonset using rhek2's embedded containerd 

```
sudo /var/lib/rancher/rke2/bin/ctr -a /run/k3s/containered/containerd.sock image pull ghcr.io/kube-vip/kube-vip:$KVVERSION
```

```
sudo /var/lib/rancher/rke2/bin/ctr -a /run/k3s/containerd/containerd.sock run --rm --net-host ghcr.io/kube-vip/kube-vip:$KVVERSION vip /kube-vip manifest daemonset \
    --interface $INTERFACE \
    --address $VIP \
    --inCluster \
    --taint \
    --controlplane \
    --services \
    --arp \
    --leaderElection | sudo tee /var/lib/rancher/rke2/server/manifests/kube-vip.yaml > /dev/null
```

verify
```
kubectl get pods -n kube-system | grep kube-vip
```
output
```
ubuntu@control1:~$ kubectl get pods -n kube-system | grep kube-vip
kube-vip-ds-2j4sz                                       1/1     Running     0             7m5s
kube-vip-ds-9c4jd                                       1/1     Running     0             7m5s
kube-vip-ds-wds95                                       1/1     Running     0             7m5s
ubuntu@control1:~$ 
```
The VIP should be reachable for your admin machine
```
❯ ping 192.168.2.12                                                                                                                                                                        ─╯
PING 192.168.2.12 (192.168.2.12) 56(84) bytes of data.
64 bytes from 192.168.2.12: icmp_seq=1 ttl=64 time=2.01 ms
64 bytes from 192.168.2.12: icmp_seq=2 ttl=64 time=0.476 ms
^C
```

## Option: Running Ollama directly on worker1 node

```
>>> Installing ollama to /usr/local
[sudo] password for ubuntu: 
>>> Downloading ollama-linux-amd64.tar.zst
######################################################################## 100.0%
>>> Creating ollama user...
>>> Adding ollama user to render group...
>>> Adding ollama user to video group...
>>> Adding current user to ollama group...
>>> Creating ollama systemd service...
>>> Enabling and starting ollama service...
Created symlink /etc/systemd/system/default.target.wants/ollama.service → /etc/systemd/system/ollama.service.
>>> The Ollama API is now available at 127.0.0.1:11434.
>>> Install complete. Run "ollama" from the command line.
WARNING: No NVIDIA/AMD GPU detected. Ollama will run in CPU-only mode.
ubuntu@worker1:~$ ollama pull qwen2.5-coder:1.5b
pulling manifest 
pulling 29d8c98fa6b0: 100% ▕██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████▏ 986 MB                         
pulling 66b9ea09bd5b: 100% ▕██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████▏   68 B
```

output:

```
ubuntu@worker1:~$ ollama run qwen2.5-coder:1.5b
>>> /set parameter num_ctx 16384
Set parameter 'num_ctx' to '16384'
>>> /save qwen2.5-coder:1.5b-16k
Created new model 'qwen2.5-coder:1.5b-16k'
>>> /bye
ubuntu@worker1:~$ curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:1.5b-16k",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
{"id":"chatcmpl-566","object":"chat.completion","created":1774852592,"model":"qwen2.5-coder:1.5b-16k","system_fingerprint":"fp_ollama","choices":[{"index":0,"message":{"role":"assistant","content":"Hello! How can I assist you today? Please let me know if you have any questions or need information on something specific."},"finish_reason":"stop"}],"usage":{"prompt_tokens":30,"completion_tokens":26,"total_tokens":56}}
```

Make sure Ollama Environment is set to listen to request from other servers then local.

```
ubuntu@worker1:~$ sudo EDITOR=vim systemctl edit ollama
ubuntu@worker1:~$ sudo systemctl restart ollama
ubuntu@worker1:~$ sudo systemctl status ollama
● ollama.service - Ollama Service
     Loaded: loaded (/etc/systemd/system/ollama.service; enabled; preset: enabled)
     Active: active (running) since Mon 2026-03-30 06:46:20 UTC; 5s ago
   Main PID: 5815 (ollama)
      Tasks: 12 (limit: 9430)
     Memory: 12.2M (peak: 24.1M)
        CPU: 87ms
     CGroup: /system.slice/ollama.service
             └─5815 /usr/local/bin/ollama serve

Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.740Z level=INFO source=routes.go:1744 msg="Ollama cloud disabled: false"
Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.741Z level=INFO source=images.go:477 msg="total blobs: 7"
Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.741Z level=INFO source=images.go:484 msg="total unused blobs removed: 0"
Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.742Z level=INFO source=routes.go:1800 msg="Listening on 127.0.0.1:11434 (version 0.19.0)"
Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.743Z level=INFO source=runner.go:67 msg="discovering available GPUs..."
Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.743Z level=INFO source=server.go:432 msg="starting runner" cmd="/usr/local/bin/ollama runner --ollama-engine --port 35207"
Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.782Z level=INFO source=server.go:432 msg="starting runner" cmd="/usr/local/bin/ollama runner --ollama-engine --port 34133"
Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.815Z level=INFO source=runner.go:106 msg="experimental Vulkan support disabled.  To enable, set OLLAMA_VULKAN=1"
Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.815Z level=INFO source=types.go:60 msg="inference compute" id=cpu library=cpu compute="" name=cpu description=cpu libdirs=ollama driver="" pci_id="" type="" total="7.8 GiB" available="6.7 GiB"
Mar 30 06:46:20 worker1 ollama[5815]: time=2026-03-30T06:46:20.815Z level=INFO source=routes.go:1850 msg="vram-based default context" total_vram="0 B" default_num_ctx=4096
ubuntu@worker1:~$ sudo ss -tlnp | grep 11434
LISTEN 0      4096       127.0.0.1:11434      0.0.0.0:*    users:(("ollama",pid=5815,fd=3)) 
```



