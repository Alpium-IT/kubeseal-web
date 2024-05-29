# About
A simple web-gui for Bitnami's kubeseal / sealed-secrets, based on [nicegui](https://nicegui.io/).
## Features
- Encrypt multiple secrets all at once.
- Supports encrypting for multiple clusters with different encryption keys.
- Fetches encryption key via http/s from the sealed-secrets controller URL
- Generates the encrypted string + the complete *sealed-secrets* manifest
- Copy buttons for easy *copy & paste* of encrypted strings.
- Configurable settings and cluster URLs in *config.yaml*




# Building

## Prereqs:
- Download kubeseal and unpack to bin/ directory!  
  Example for kubeseal v0.26.3:
    ```
    cd bin && \
    curl  -o ks.tgz -L https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.26.3/kubeseal-0.26.3-linux-amd64.tar.gz \
    && tar xzf ks.tgz kubeseal \
    && rm ks.tgz
    ```
 -  Build image and push to your registry, eg:
    ```
    docker buildx build --push
    ```
 
 
# Deploying
## k8s
- Uses *kustomize*. Modify/create overlay if required.
- Deploys to namespace `sealed-secrets` by default!  

```
kustomize build k8s/base | kubectl apply -f -
```

# Configuration
## config.yaml

```
# clusters dictionary
# 
# CLUSTERNAME:
#    url: <URL OF SEALED-SECRETS ROUTE>
#    namespacePrefix: "dev-"  # will be prepended to the namespace's name
#    enabled: true | false    # set the cluste's checkbox to checked or unchecked initially

defaults:
  enable-cluster-wide-encryption: true
  max-secrets: 5

clusters:
  east:
    url: http://cert.sealedsecrets.east.example.com/v1/cert.pem
    namespacePrefix: east-
    enabled: true

  west:
    url: http://cert.sealedsecrets.west.example.com/v1/cert.pem
    enabled: false
    namespacePrefix: west-

  global:
    url: http://cert.sealedsecrets.global.example.com/v1/cert.pem
    enabled: false


```