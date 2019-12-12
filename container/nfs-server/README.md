# NFS-exporter container with a file

This container exports `/exported-artifacts` via NFS. Since some Linux kernels
have issues running NFSv4 daemons in containers, only NFSv3 is opened in this
container.
