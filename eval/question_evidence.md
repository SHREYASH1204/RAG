# Evaluation Draft Grounding Evidence

This document provides verbatim quotes, chunk IDs, and grep absence verification for all 44 evaluation draft questions in `eval/eval_draft.jsonl`.

## Q-001: How many minor versions may the kubelet lag behind kube-apiserver?
- **Type**: `version_conflict`
- **Status**: `yes`
- **Gold Docs**: `['releases/version-skew-policy']`
- **Must Include**: `['two', 'three']`
- **Expected Answer**: In 1.27, kubelet may be up to two minor versions older than kube-apiserver. In 1.31, kubelet may be up to three minor versions older than kube-apiserver (kubelet < 1.25 may only be up to two minor versions older).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:releases/version-skew-policy#c3` (`Version Skew Policy > Supported version skew > kubelet`)
  > "kubelet must not be newer than kube-apiserver, and may be up to two minor versions older. Example: kube-apiserver is at 1.27 kubelet is supported at 1.27, 1.26, and 1.25 Note: If version skew exists between kube-apiserver instances in an HA cluster, this narrows the allowed kubelet versions. Example: kube-apiserver instances are at 1.27 and 1.26 kubelet is supported at 1.26, and 1.25 (1.27 is not supported because that would be newer than the kube-apiserver instance at version 1.26)"

#### Version 1.31
- **Chunk ID**: `v1.31:releases/version-skew-policy#c3` (`Version Skew Policy > Supported version skew > kubelet`)
  > "kubelet must not be newer than kube-apiserver. kubelet may be up to three minor versions older than kube-apiserver (kubelet < 1.25 may only be up to two minor versions older than kube-apiserver). Example: kube-apiserver is at 1.31 kubelet is supported at 1.31, 1.30, 1.29, and 1.28 Note: If version skew exists between kube-apiserver instances in an HA cluster, this narrows the allowed kubelet versions. Example: kube-apiserver instances are at 1.31 and 1.30 kubelet is supported at 1.30, 1.29, and 1.28 (1.31 is not supported because that would be newer than the kube-apiserver instance at version "

---

## Q-002: How far behind kube-apiserver can kube-proxy be?
- **Type**: `version_conflict`
- **Status**: `yes`
- **Gold Docs**: `['releases/version-skew-policy']`
- **Must Include**: `['two', 'three']`
- **Expected Answer**: In 1.27, kube-proxy may be up to two minor versions older than kube-apiserver. In 1.31, kube-proxy may be up to three minor versions older than kube-apiserver (kube-proxy < 1.25 may only be up to two minor versions older).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:releases/version-skew-policy#c4` (`Version Skew Policy > Supported version skew > kube-proxy`)
  > "kube-proxy must not be newer than kube-apiserver, and may be up to two minor versions older. kube-proxy may be up to two minor versions older or newer than the kubelet instance it runs alongside. Example: kube-apiserver is at 1.27 kube-proxy is supported at 1.27, 1.26, and 1.25 Note: If version skew exists between kube-apiserver instances in an HA cluster, this narrows the allowed kube-proxy versions. Example: kube-apiserver instances are at 1.27 and 1.26 kube-proxy is supported at 1.26, and 1.25 (1.27 is not supported because that would be newer than the kube-apiserver instance at version 1.2"

#### Version 1.31
- **Chunk ID**: `v1.31:releases/version-skew-policy#c4` (`Version Skew Policy > Supported version skew > kube-proxy`)
  > "kube-proxy must not be newer than kube-apiserver. kube-proxy may be up to three minor versions older than kube-apiserver (kube-proxy < 1.25 may only be up to two minor versions older than kube-apiserver). kube-proxy may be up to three minor versions older or newer than the kubelet instance it runs alongside (kube-proxy < 1.25 may only be up to two minor versions older or newer than the kubelet instance it runs alongside). Example: kube-apiserver is at 1.31 kube-proxy is supported at 1.31, 1.30, 1.29, and 1.28 Note: If version skew exists between kube-apiserver instances in an HA cluster, this "

---

## Q-003: What is the feature state of the Pod failure policy for Jobs?
- **Type**: `version_conflict`
- **Status**: `yes`
- **Gold Docs**: `['tasks/job/pod-failure-policy']`
- **Must Include**: `['beta', 'stable']`
- **Expected Answer**: In 1.27, the Pod failure policy for Jobs is beta (v1.26 [beta]). In 1.31, the Pod failure policy for Jobs is stable (v1.31 [stable]).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:tasks/job/pod-failure-policy#c0` (`Handling retriable and non-retriable pod failures with Pod failure policy`)
  > "FEATURE STATE: Kubernetes v1.26 [beta] This document shows you how to use the Pod failure policy, in combination with the default Pod backoff failure policy, to improve the control over the handling of container- or Pod-level failure within a Job. The definition of Pod failure policy may help you to: better utilize the computational resources by avoiding unnecessary Pod retries. avoid Job failures due to Pod disruptions (such preemption, API-initiated eviction or taint-based eviction)."

#### Version 1.31
- **Chunk ID**: `v1.31:tasks/job/pod-failure-policy#c0` (`Handling retriable and non-retriable pod failures with Pod failure policy`)
  > "FEATURE STATE: Kubernetes v1.31 [stable] This document shows you how to use the Pod failure policy, in combination with the default Pod backoff failure policy, to improve the control over the handling of container- or Pod-level failure within a Job. The definition of Pod failure policy may help you to: better utilize the computational resources by avoiding unnecessary Pod retries. avoid Job failures due to Pod disruptions (such preemption, API-initiated eviction or taint-based eviction)."

---

## Q-004: What is the feature state of the ReadWriteOncePod access mode for PersistentVolumes?
- **Type**: `version_conflict`
- **Status**: `yes`
- **Gold Docs**: `['concepts/storage/persistent-volumes']`
- **Must Include**: `['beta', 'stable']`
- **Expected Answer**: In 1.27, ReadWriteOncePod is beta (Kubernetes v1.27 [beta]). In 1.31, ReadWriteOncePod is stable (Kubernetes v1.29 [stable]).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/storage/persistent-volumes#c24` (`Persistent Volumes > Persistent Volumes > Access Modes`)
  > "A PersistentVolume can be mounted on a host in any way supported by the resource provider. As shown in the table below, providers will have different capabilities and each PV's access modes are set to the specific modes supported by that particular volume. For example, NFS can support multiple read/write clients, but a specific NFS PV might be exported on the server as read-only. Each PV gets its own set of access modes describing that specific PV's capabilities. The access modes are: ReadWriteOnce : the volume can be mounted as read-write by a single node. ReadWriteOnce access mode still can "

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/storage/persistent-volumes#c24` (`Persistent Volumes > Persistent Volumes > Access Modes`)
  > "A PersistentVolume can be mounted on a host in any way supported by the resource provider. As shown in the table below, providers will have different capabilities and each PV's access modes are set to the specific modes supported by that particular volume. For example, NFS can support multiple read/write clients, but a specific NFS PV might be exported on the server as read-only. Each PV gets its own set of access modes describing that specific PV's capabilities. The access modes are: ReadWriteOnce : the volume can be mounted as read-write by a single node. ReadWriteOnce access mode still can "

---

## Q-005: What is the feature state of Pod scheduling readiness (scheduling gates)?
- **Type**: `version_conflict`
- **Status**: `yes`
- **Gold Docs**: `['concepts/scheduling-eviction/pod-scheduling-readiness']`
- **Must Include**: `['alpha', 'stable']`
- **Expected Answer**: In 1.27, Pod scheduling readiness is alpha (v1.26 [alpha]). In 1.31, Pod scheduling readiness is stable (v1.30 [stable]).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/scheduling-eviction/pod-scheduling-readiness#c0` (`Pod Scheduling Readiness`)
  > "FEATURE STATE: Kubernetes v1.26 [alpha] Pods were considered ready for scheduling once created. Kubernetes scheduler does its due diligence to find nodes to place all pending Pods. However, in a real-world case, some Pods may stay in a "miss-essential-resources" state for a long period. These Pods actually churn the scheduler (and downstream integrators like Cluster AutoScaler) in an unnecessary manner. By specifying/removing a Pod's .spec.schedulingGates, you can control when a Pod is ready to be considered for scheduling."

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/scheduling-eviction/pod-scheduling-readiness#c0` (`Pod Scheduling Readiness`)
  > "FEATURE STATE: Kubernetes v1.30 [stable] Pods were considered ready for scheduling once created. Kubernetes scheduler does its due diligence to find nodes to place all pending Pods. However, in a real-world case, some Pods may stay in a "miss-essential-resources" state for a long period. These Pods actually churn the scheduler (and downstream integrators like Cluster AutoScaler) in an unnecessary manner. By specifying/removing a Pod's .spec.schedulingGates, you can control when a Pod is ready to be considered for scheduling."

---

## Q-006: Is swap memory supported on Kubernetes nodes, and what is its feature state?
- **Type**: `version_conflict`
- **Status**: `yes`
- **Gold Docs**: `['concepts/architecture/nodes']`
- **Must Include**: `['alpha', 'beta']`
- **Expected Answer**: In 1.27, swap memory support on nodes is alpha (v1.22 [alpha]). In 1.31, swap memory support is beta (v1.30 [beta]).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/architecture/nodes#c18` (`Nodes > Swap memory management`)
  > "FEATURE STATE: Kubernetes v1.22 [alpha] Prior to Kubernetes 1.22, nodes did not support the use of swap memory, and a kubelet would by default fail to start if swap was detected on a node. In 1.22 onwards, swap memory support can be enabled on a per-node basis. To enable swap on a node, the NodeSwap feature gate must be enabled on the kubelet, and the --fail-swap-on command line flag or failSwapOn configuration setting must be set to false. Warning: When the memory swap feature is turned on, Kubernetes data such as the content of Secret objects that were written to tmpfs now could be swapped t"

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/architecture/nodes#c11` (`Nodes > Swap memory management`)
  > "FEATURE STATE: Kubernetes v1.30 [beta] To enable swap on a node, the NodeSwap feature gate must be enabled on the kubelet (default is true), and the --fail-swap-on command line flag or failSwapOn configuration setting must be set to false. To allow Pods to utilize swap, swapBehavior should not be set to NoSwap (which is the default behavior) in the kubelet config. Warning: When the memory swap feature is turned on, Kubernetes data such as the content of Secret objects that were written to tmpfs now could be swapped to disk. A user can also optionally configure memorySwap.swapBehavior in order "

---

## Q-007: Which API version do the FlowSchema and PriorityLevelConfiguration examples use?
- **Type**: `version_conflict`
- **Status**: `yes`
- **Gold Docs**: `['concepts/cluster-administration/flow-control']`
- **Must Include**: `['v1beta3', 'v1']`
- **Expected Answer**: In 1.27, FlowSchema and PriorityLevelConfiguration examples use apiVersion flowcontrol.apiserver.k8s.io/v1beta3. In 1.31, they use flowcontrol.apiserver.k8s.io/v1.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/cluster-administration/flow-control#c15` (`API Priority and Fairness > Health check concurrency exemption`)
  > "The suggested configuration gives no special treatment to the health check requests on kube-apiservers from their local kubelets --- which tend to use the secured port but supply no credentials. With the suggested config, these requests get assigned to the global-default FlowSchema and the corresponding global-default priority level, where other traffic can crowd them out. If you add the following additional FlowSchema, this exempts those requests from rate limiting. Caution: Making this change also allows any hostile party to then send health-check requests that match this FlowSchema, at any "

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/cluster-administration/flow-control#c16` (`API Priority and Fairness > Health check concurrency exemption`)
  > "The suggested configuration gives no special treatment to the health check requests on kube-apiservers from their local kubelets --- which tend to use the secured port but supply no credentials. With the suggested config, these requests get assigned to the global-default FlowSchema and the corresponding global-default priority level, where other traffic can crowd them out. If you add the following additional FlowSchema, this exempts those requests from rate limiting. Caution: Making this change also allows any hostile party to then send health-check requests that match this FlowSchema, at any "

---

## Q-008: What is the feature state of the start ordinal (.spec.ordinals.start) field for StatefulSets?
- **Type**: `version_conflict`
- **Status**: `replaced`
- **Gold Docs**: `['concepts/workloads/controllers/statefulset']`
- **Must Include**: `['beta', 'stable']`
- **Expected Answer**: In 1.27, the start ordinal field for StatefulSets is beta (v1.27 [beta]). In 1.31, it is stable (v1.31 [stable]).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/workloads/controllers/statefulset#c9` (`StatefulSets > Pod Identity > Start ordinal`)
  > "FEATURE STATE: Kubernetes v1.27 [beta] .spec.ordinals is an optional field that allows you to configure the integer ordinals assigned to each Pod. It defaults to nil. You must enable the StatefulSetStartOrdinal feature gate to use this field. Once enabled, you can configure the following options: * .spec.ordinals.start: If the .spec.ordinals.start field is set, Pods will be assigned ordinals from .spec.ordinals.start up through .spec.ordinals.start + .spec.replicas - 1."

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/controllers/statefulset#c9` (`StatefulSets > Pod Identity > Start ordinal`)
  > "FEATURE STATE: Kubernetes v1.31 [stable] .spec.ordinals is an optional field that allows you to configure the integer ordinals assigned to each Pod. It defaults to nil. Within the field, you can configure the following options: * .spec.ordinals.start: If the .spec.ordinals.start field is set, Pods will be assigned ordinals from .spec.ordinals.start up through .spec.ordinals.start + .spec.replicas - 1."

---

## Q-009: What is the feature state of the UnhealthyPodEvictionPolicy for PodDisruptionBudgets?
- **Type**: `version_conflict`
- **Status**: `replaced`
- **Gold Docs**: `['concepts/workloads/pods/disruptions']`
- **Must Include**: `['beta', 'stable']`
- **Expected Answer**: In 1.27, UnhealthyPodEvictionPolicy for PodDisruptionBudgets is beta (v1.27 [beta]). In 1.31, it is stable (v1.31 [stable]).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/workloads/pods/disruptions#c14` (NOT FOUND IN INDEX)

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/pods/disruptions#c14` (NOT FOUND IN INDEX)

---

## Q-010: What is the feature state of Container resource metrics in HorizontalPodAutoscaler?
- **Type**: `version_conflict`
- **Status**: `replaced`
- **Gold Docs**: `['tasks/run-application/horizontal-pod-autoscale']`
- **Must Include**: `['beta', 'stable']`
- **Expected Answer**: In 1.27, Container resource metrics in HorizontalPodAutoscaler is beta (v1.27 [beta]). In 1.31, it is stable (v1.30 [stable]).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:tasks/run-application/horizontal-pod-autoscale#c5` (`Horizontal Pod Autoscaling > Autoscaling during rolling update`)
  > "Kubernetes lets you perform a rolling update on a Deployment. In that case, the Deployment manages the underlying ReplicaSets for you. When you configure autoscaling for a Deployment, you bind a HorizontalPodAutoscaler to a single Deployment. The HorizontalPodAutoscaler manages the replicas field of the Deployment. The deployment controller is responsible for setting the replicas of the underlying ReplicaSets so that they add up to a suitable number during the rollout and also afterwards. If you perform a rolling update of a StatefulSet that has an autoscaled number of replicas, the StatefulSe"

#### Version 1.31
- **Chunk ID**: `v1.31:tasks/run-application/horizontal-pod-autoscale#c5` (`Horizontal Pod Autoscaling > Autoscaling during rolling update`)
  > "Kubernetes lets you perform a rolling update on a Deployment. In that case, the Deployment manages the underlying ReplicaSets for you. When you configure autoscaling for a Deployment, you bind a HorizontalPodAutoscaler to a single Deployment. The HorizontalPodAutoscaler manages the replicas field of the Deployment. The deployment controller is responsible for setting the replicas of the underlying ReplicaSets so that they add up to a suitable number during the rollout and also afterwards. If you perform a rolling update of a StatefulSet that has an autoscaled number of replicas, the StatefulSe"

---

## Q-011: What does the kubernetes.io/enforce-mountable-secrets annotation do on a ServiceAccount?
- **Type**: `only_in_one_version`
- **Status**: `yes`
- **Gold Docs**: `['concepts/configuration/secret', 'concepts/security/service-accounts']`
- **Must Include**: `['secrets', '1.31']`
- **Expected Answer**: Documented only in Kubernetes 1.31. The annotation indicates that Secrets mounted as volumes, referenced via envFrom, or via imagePullSecrets must be listed in the ServiceAccount's secrets field. It is not documented in Kubernetes 1.27.

### Verbatim Evidence from Corpus Chunks

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/configuration/secret#c29` (`Secrets > Information security for Secrets > Configure least-privilege access to Secrets`)
  > "To enhance the security measures around Secrets, Kubernetes provides a mechanism: you can annotate a ServiceAccount as kubernetes.io/enforce-mountable-secrets: "true". For more information, you can refer to the documentation about this annotation. Warning: Any containers that run with privileged: true on a node can access all Secrets used on that node."

### Absence Verification (Grep Results across Corpus)

- **Term**: `"enforce-mountable-secrets"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **3** hits

---

## Q-012: How do I define a sidecar container in a Pod?
- **Type**: `only_in_one_version`
- **Status**: `yes`
- **Gold Docs**: `['concepts/workloads/pods/sidecar-containers']`
- **Must Include**: `['initContainers', 'restartPolicy', 'Always']`
- **Expected Answer**: Documented only in Kubernetes 1.31. Sidecar containers are defined as init containers with restartPolicy set to Always. Native sidecar container lifecycle is not documented in Kubernetes 1.27.

### Verbatim Evidence from Corpus Chunks

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/pods/sidecar-containers#c1` (`Sidecar Containers > Sidecar containers in Kubernetes`)
  > "Kubernetes implements sidecar containers as a special case of init containers; sidecar containers remain running after Pod startup. This document uses the term regular init containers to clearly refer to containers that only run during Pod startup. Provided that your cluster has the SidecarContainers feature gate enabled (the feature is active by default since Kubernetes v1.29), you can specify a restartPolicy for containers listed in a Pod's initContainers field. These restartable sidecar containers are independent from other init containers and from the main application container(s) within t"

### Absence Verification (Grep Results across Corpus)

- **Term**: `"concepts/workloads/pods/sidecar-containers"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-013: What is a VolumeAttributesClass?
- **Type**: `only_in_one_version`
- **Status**: `yes`
- **Gold Docs**: `['concepts/storage/volume-attributes-classes']`
- **Must Include**: `['VolumeAttributesClass', 'PersistentVolumes']`
- **Expected Answer**: Documented only in Kubernetes 1.31. A VolumeAttributesClass allows cluster administrators to describe the classes of storage properties that users can modify for PersistentVolumes. It is not documented in Kubernetes 1.27.

### Verbatim Evidence from Corpus Chunks

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/storage/volume-attributes-classes#c0` (`Volume Attributes Classes`)
  > "FEATURE STATE: Kubernetes v1.31 [beta] This page assumes that you are familiar with StorageClasses, volumes and PersistentVolumes in Kubernetes. A VolumeAttributesClass provides a way for administrators to describe the mutable "classes" of storage they offer. Different classes might map to different quality-of-service levels. Kubernetes itself is un-opinionated about what these classes represent. This is a beta feature and disabled by default. If you want to test the feature whilst it's beta, you need to enable the VolumeAttributesClass feature gate for the kube-controller-manager, kube-schedu"

### Absence Verification (Grep Results across Corpus)

- **Term**: `"VolumeAttributesClass"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **6** hits

---

## Q-014: How do I use an image volume in a Pod?
- **Type**: `only_in_one_version`
- **Status**: `yes`
- **Gold Docs**: `['tasks/configure-pod-container/image-volumes', 'concepts/storage/volumes']`
- **Must Include**: `['image', 'volume']`
- **Expected Answer**: Documented only in Kubernetes 1.31. An image volume allows you to mount the content of an OCI container image directly into a Pod as a volume by specifying the image field under volumes. It is not documented in Kubernetes 1.27.

### Verbatim Evidence from Corpus Chunks

#### Version 1.31
- **Chunk ID**: `v1.31:tasks/configure-pod-container/image-volumes#c0` (`Use an Image Volume With a Pod`)
  > "FEATURE STATE: Kubernetes v1.31 [alpha] This page shows how to configure a pod using image volumes. This allows you to mount content from OCI registries inside containers."

### Absence Verification (Grep Results across Corpus)

- **Term**: `"tasks/configure-pod-container/image-volumes"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-015: What is the mixed version proxy?
- **Type**: `only_in_one_version`
- **Status**: `yes`
- **Gold Docs**: `['concepts/architecture/mixed-version-proxy']`
- **Must Include**: `['proxy', 'apiserver']`
- **Expected Answer**: Documented only in Kubernetes 1.31. The mixed version proxy enables an apiserver to proxy HTTP resource requests to other peer apiservers in a cluster running different Kubernetes versions. It is not documented in Kubernetes 1.27.

### Verbatim Evidence from Corpus Chunks

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/architecture/mixed-version-proxy#c0` (`Mixed Version Proxy`)
  > "FEATURE STATE: Kubernetes v1.28 [alpha] Kubernetes 1.31 includes an alpha feature that lets an API Server proxy a resource requests to other peer API servers. This is useful when there are multiple API servers running different versions of Kubernetes in one cluster (for example, during a long-lived rollout to a new release of Kubernetes). This enables cluster administrators to configure highly available clusters that can be upgraded more safely, by directing resource requests (made during the upgrade) to the correct kube-apiserver. That proxying prevents users from seeing unexpected 404 Not Fo"

### Absence Verification (Grep Results across Corpus)

- **Term**: `"concepts/architecture/mixed-version-proxy"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-016: What is the per-cluster licence cost of Kubernetes?
- **Type**: `unanswerable`
- **Status**: `yes`
- **Gold Docs**: `[]`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation does not contain information about per-cluster licence costs or pricing for Kubernetes.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"licence cost"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"license cost"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"pricing"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-017: What is the maximum number of custom scheduler profiles allowed in a KubeSchedulerConfiguration?
- **Type**: `unanswerable`
- **Status**: `replaced`
- **Gold Docs**: `['tasks/extend-kubernetes/configure-multiple-schedulers', 'concepts/scheduling-eviction/kube-scheduler']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation does not specify a maximum limit on the number of scheduler profiles allowed in a KubeSchedulerConfiguration.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"maximum number of profiles"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"profile limit"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"maximum profiles"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-018: What is the default maximum number of Services allowed per namespace?
- **Type**: `unanswerable`
- **Status**: `yes`
- **Gold Docs**: `['concepts/services-networking/service']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation does not state a default maximum number of Services permitted per namespace.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"maximum number of services"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"max services per namespace"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-019: Which kubectl command shows the monetary cost of a namespace?
- **Type**: `unanswerable`
- **Status**: `yes`
- **Gold Docs**: `['concepts/overview/working-with-objects/namespaces']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation does not describe any kubectl command for calculating monetary costs of namespaces.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"monetary cost"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"kubectl cost"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-020: How much memory does kube-apiserver need per 1000 nodes?
- **Type**: `unanswerable`
- **Status**: `yes`
- **Gold Docs**: `['concepts/overview/components']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation does not specify the exact memory requirement of kube-apiserver per 1000 nodes.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"per 1000 nodes"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"memory for 1000 nodes"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-021: Which cloud provider does Kubernetes recommend for production clusters?
- **Type**: `unanswerable`
- **Status**: `yes`
- **Gold Docs**: `['concepts/architecture']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation does not recommend any specific cloud provider for production clusters.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"recommend AWS"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"recommend GCP"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"recommended cloud provider"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-022: What is the maximum size of a ConfigMap when the etcd quota has been raised?
- **Type**: `unanswerable`
- **Status**: `yes`
- **Gold Docs**: `['concepts/configuration/configmap']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation states the 1 MiB limit but does not document an alternative maximum ConfigMap size for raised etcd quotas.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"ConfigMap when the etcd quota"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"quota has been raised"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-023: What is the default value of the kubelet --image-gc-high-threshold flag?
- **Type**: `unanswerable`
- **Status**: `yes`
- **Gold Docs**: `['concepts/scheduling-eviction/node-pressure-eviction']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation references the deprecated --image-gc-high-threshold flag but does not state its default value.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"--image-gc-high-threshold default"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-024: Does enforce-mountable-secrets also restrict Secrets used in projected volumes?
- **Type**: `unanswerable`
- **Status**: `yes`
- **Gold Docs**: `['concepts/configuration/secret', 'concepts/storage/projected-volumes']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation describes restricting volumes, envFrom, and imagePullSecrets, but does not state whether projected volumes are restricted.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"enforce-mountable-secrets projected"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-025: Which Linux distribution does Kubernetes recommend for control plane nodes?
- **Type**: `unanswerable`
- **Status**: `yes`
- **Gold Docs**: `['concepts/architecture/nodes']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The documentation does not recommend a specific Linux distribution for control plane nodes.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"recommend Ubuntu"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

- **Term**: `"recommended Linux distribution"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-026: How do I set the kubernetes.io/enforce-mountable-configmaps annotation?
- **Type**: `false_premise`
- **Status**: `yes`
- **Gold Docs**: `['concepts/configuration/configmap']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The annotation kubernetes.io/enforce-mountable-configmaps is not documented in Kubernetes 1.27 or 1.31.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"enforce-mountable-configmaps"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-027: What does kubectl get pods --sort-by-age do?
- **Type**: `false_premise`
- **Status**: `yes`
- **Gold Docs**: `['reference/kubectl/cheatsheet']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The flag --sort-by-age is not documented in Kubernetes 1.27 or 1.31.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"--sort-by-age"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-028: How do I set the spec.restartDelaySeconds field on a Pod?
- **Type**: `false_premise`
- **Status**: `yes`
- **Gold Docs**: `['concepts/workloads/pods/pod-lifecycle']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The field spec.restartDelaySeconds is not documented in Kubernetes 1.27 or 1.31.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"restartDelaySeconds"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-029: What does the --enable-pod-priority-classes flag do?
- **Type**: `false_premise`
- **Status**: `yes`
- **Gold Docs**: `['concepts/scheduling-eviction/pod-priority-preemption']`
- **Must Include**: `[]`
- **Expected Answer**: Refusal: The flag --enable-pod-priority-classes is not documented in Kubernetes 1.27 or 1.31.

### Absence Verification (Grep Results across Corpus)

- **Term**: `"--enable-pod-priority-classes"`
  - 1.27 matches: **0** hits
  - 1.31 matches: **0** hits

---

## Q-030: What is a Pod?
- **Type**: `same_in_both`
- **Status**: `yes`
- **Gold Docs**: `['concepts/workloads/pods/_index']`
- **Must Include**: `['smallest', 'containers']`
- **Expected Answer**: Pods are the smallest deployable units of computing that you can create and manage in Kubernetes, representing a group of one or more containers with shared storage and network resources.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/workloads/pods/_index#c0` (`Pods`)
  > "Pods are the smallest deployable units of computing that you can create and manage in Kubernetes. A Pod (as in a pod of whales or pea pod) is a group of one or more containers, with shared storage and network resources, and a specification for how to run the containers. A Pod's contents are always co-located and co-scheduled, and run in a shared context. A Pod models an application-specific "logical host": it contains one or more application containers which are relatively tightly coupled. In non-cloud contexts, applications executed on the same physical or virtual machine are analogous to clo"

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/pods/_index#c0` (`Pods`)
  > "Pods are the smallest deployable units of computing that you can create and manage in Kubernetes. A Pod (as in a pod of whales or pea pod) is a group of one or more containers, with shared storage and network resources, and a specification for how to run the containers. A Pod's contents are always co-located and co-scheduled, and run in a shared context. A Pod models an application-specific "logical host": it contains one or more application containers which are relatively tightly coupled. In non-cloud contexts, applications executed on the same physical or virtual machine are analogous to clo"

---

## Q-031: What does kube-scheduler do?
- **Type**: `same_in_both`
- **Status**: `yes`
- **Gold Docs**: `['concepts/scheduling-eviction/kube-scheduler']`
- **Must Include**: `['matched', 'Nodes']`
- **Expected Answer**: In Kubernetes, kube-scheduler is responsible for scheduling, which refers to making sure that Pods are matched to Nodes so that kubelet can run them.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/scheduling-eviction/kube-scheduler#c0` (`Kubernetes Scheduler`)
  > "In Kubernetes, scheduling refers to making sure that Pods are matched to Nodes so that Kubelet can run them."

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/scheduling-eviction/kube-scheduler#c0` (`Kubernetes Scheduler`)
  > "In Kubernetes, scheduling refers to making sure that Pods are matched to Nodes so that Kubelet can run them."

---

## Q-032: How does a Deployment perform a rolling update?
- **Type**: `same_in_both`
- **Status**: `yes`
- **Gold Docs**: `['concepts/workloads/controllers/deployment']`
- **Must Include**: `['declarative', 'ReplicaSets']`
- **Expected Answer**: A Deployment updates Pods by changing the actual state to the desired state at a controlled rate, creating a new ReplicaSet and transitioning Pods while maintaining availability.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/workloads/controllers/deployment#c0` (`Deployments`)
  > "A Deployment provides declarative updates for Pods and ReplicaSets. You describe a desired state in a Deployment, and the Deployment Controller changes the actual state to the desired state at a controlled rate. You can define Deployments to create new ReplicaSets, or to remove existing Deployments and adopt all their resources with new Deployments. Note: Do not manage ReplicaSets owned by a Deployment. Consider opening an issue in the main Kubernetes repository if your use case is not covered below."

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/controllers/deployment#c0` (`Deployments`)
  > "A Deployment provides declarative updates for Pods and ReplicaSets. You describe a desired state in a Deployment, and the Deployment Controller changes the actual state to the desired state at a controlled rate. You can define Deployments to create new ReplicaSets, or to remove existing Deployments and adopt all their resources with new Deployments. Note: Do not manage ReplicaSets owned by a Deployment. Consider opening an issue in the main Kubernetes repository if your use case is not covered below."

---

## Q-033: What does a Service of type ClusterIP do?
- **Type**: `same_in_both`
- **Status**: `yes`
- **Gold Docs**: `['concepts/services-networking/service']`
- **Must Include**: `['cluster-internal', 'default']`
- **Expected Answer**: A Service of type ClusterIP exposes the Service on a cluster-internal IP, making the Service only reachable from within the cluster. This is the default Service type.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/services-networking/service#c15` (`Service > Service type > type: ClusterIP > Choosing your own IP address`)
  > "You can specify your own cluster IP address as part of a Service creation request. To do this, set the .spec.clusterIP field. For example, if you already have an existing DNS entry that you wish to reuse, or legacy systems that are configured for a specific IP address and difficult to re-configure. The IP address that you choose must be a valid IPv4 or IPv6 address from within the service-cluster-ip-range CIDR range that is configured for the API server. If you try to create a Service with an invalid clusterIP address value, the API server will return a 422 HTTP status code to indicate that th"

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/services-networking/service#c15` (`Service > Service type > type: ClusterIP > Choosing your own IP address`)
  > "You can specify your own cluster IP address as part of a Service creation request. To do this, set the .spec.clusterIP field. For example, if you already have an existing DNS entry that you wish to reuse, or legacy systems that are configured for a specific IP address and difficult to re-configure. The IP address that you choose must be a valid IPv4 or IPv6 address from within the service-cluster-ip-range CIDR range that is configured for the API server. If you try to create a Service with an invalid clusterIP address value, the API server will return a 422 HTTP status code to indicate that th"

---

## Q-034: What are Namespaces used for?
- **Type**: `same_in_both`
- **Status**: `yes`
- **Gold Docs**: `['concepts/overview/working-with-objects/namespaces']`
- **Must Include**: `['isolating', 'unique']`
- **Expected Answer**: Namespaces provide a mechanism for isolating groups of resources within a single cluster, where resource names must be unique within a namespace but not across namespaces.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/overview/working-with-objects/namespaces#c0` (`Namespaces`)
  > "In Kubernetes, namespaces provides a mechanism for isolating groups of resources within a single cluster. Names of resources need to be unique within a namespace, but not across namespaces. Namespace-based scoping is applicable only for namespaced objects (e.g. Deployments, Services, etc) and not for cluster-wide objects (e.g. StorageClass, Nodes, PersistentVolumes, etc)."

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/overview/working-with-objects/namespaces#c0` (`Namespaces`)
  > "In Kubernetes, namespaces provide a mechanism for isolating groups of resources within a single cluster. Names of resources need to be unique within a namespace, but not across namespaces. Namespace-based scoping is applicable only for namespaced objects (e.g. Deployments, Services, etc.) and not for cluster-wide objects (e.g. StorageClass, Nodes, PersistentVolumes, etc.)."

---

## Q-035: How does a ReplicaSet differ from a Deployment?
- **Type**: `same_in_both`
- **Status**: `yes`
- **Gold Docs**: `['concepts/workloads/controllers/replicaset']`
- **Must Include**: `['declarative', 'higher-level']`
- **Expected Answer**: A ReplicaSet ensures a specified number of pod replicas are running at any given time, whereas a Deployment is a higher-level concept that manages ReplicaSets and provides declarative updates to Pods.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/workloads/controllers/replicaset#c0` (`ReplicaSet`)
  > "A ReplicaSet's purpose is to maintain a stable set of replica Pods running at any given time. As such, it is often used to guarantee the availability of a specified number of identical Pods."

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/controllers/replicaset#c0` (`ReplicaSet`)
  > "A ReplicaSet's purpose is to maintain a stable set of replica Pods running at any given time. As such, it is often used to guarantee the availability of a specified number of identical Pods."

---

## Q-036: How do I create a Secret with kubectl?
- **Type**: `procedural`
- **Status**: `yes`
- **Gold Docs**: `['tasks/configmap-secret/managing-secret-using-kubectl']`
- **Must Include**: `['kubectl create secret', 'generic']`
- **Expected Answer**: You can create a Secret using kubectl create secret generic <name> with flags such as --from-literal or --from-file.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:tasks/configmap-secret/managing-secret-using-kubectl#c3` (`Managing Secrets using kubectl > Create a Secret > Use raw data`)
  > "Run the following command:  ```shell kubectl create secret generic db-user-pass \     --from-literal=username=admin \     --from-literal=password='S!B\*d$zDsb=' ```  You must use single quotes '' to escape special characters such as $, \, *, =, and ! in your strings. If you don't, your shell will interpret these characters."

#### Version 1.31
- **Chunk ID**: `v1.31:tasks/configmap-secret/managing-secret-using-kubectl#c3` (`Managing Secrets using kubectl > Create a Secret > Use raw data`)
  > "Run the following command:  ```shell kubectl create secret generic db-user-pass \     --from-literal=username=admin \     --from-literal=password='S!B\*d$zDsb=' ```  You must use single quotes '' to escape special characters such as $, \, *, =, and ! in your strings. If you don't, your shell will interpret these characters. Note: The stringData field for a Secret does not work well with server-side apply."

---

## Q-037: How do I configure an HTTP liveness probe for a container?
- **Type**: `procedural`
- **Status**: `yes`
- **Gold Docs**: `['tasks/configure-pod-container/configure-liveness-readiness-startup-probes']`
- **Must Include**: `['livenessProbe', 'httpGet']`
- **Expected Answer**: Configure a livenessProbe field in the container manifest with an httpGet section specifying the path and port to probe.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:tasks/configure-pod-container/configure-liveness-readiness-startup-probes#c4` (`Configure Liveness, Readiness and Startup Probes > Define a TCP liveness probe`)
  > "A third type of liveness probe uses a TCP socket. With this configuration, the kubelet will attempt to open a socket to your container on the specified port. If it can establish a connection, the container is considered healthy, if it can't it is considered a failure.  ```yaml apiVersion: v1 kind: Pod metadata:   name: goproxy   labels:     app: goproxy spec:   containers:   - name: goproxy     image: registry.k8s.io/goproxy:0.1     ports:     - containerPort: 8080     readinessProbe:       tcpSocket:         port: 8080       initialDelaySeconds: 5       periodSeconds: 10     livenessProbe:   "

#### Version 1.31
- **Chunk ID**: `v1.31:tasks/configure-pod-container/configure-liveness-readiness-startup-probes#c4` (`Configure Liveness, Readiness and Startup Probes > Define a TCP liveness probe`)
  > "A third type of liveness probe uses a TCP socket. With this configuration, the kubelet will attempt to open a socket to your container on the specified port. If it can establish a connection, the container is considered healthy, if it can't it is considered a failure.  ```yaml apiVersion: v1 kind: Pod metadata:   name: goproxy   labels:     app: goproxy spec:   containers:   - name: goproxy     image: registry.k8s.io/goproxy:0.1     ports:     - containerPort: 8080     readinessProbe:       tcpSocket:         port: 8080       initialDelaySeconds: 15       periodSeconds: 10     livenessProbe:  "

---

## Q-038: How do I taint a node so Pods are not scheduled on it?
- **Type**: `procedural`
- **Status**: `yes`
- **Gold Docs**: `['concepts/scheduling-eviction/taint-and-toleration']`
- **Must Include**: `['kubectl taint', 'NoSchedule']`
- **Expected Answer**: Apply a taint to the node using the command: kubectl taint nodes <nodename> <key>=<value>:<effect>, for example using effect NoSchedule.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/scheduling-eviction/taint-and-toleration#c0` (`Taints and Tolerations`)
  > "Node affinity is a property of Pods that attracts them to a set of nodes (either as a preference or a hard requirement). Taints are the opposite -- they allow a node to repel a set of pods. Tolerations are applied to pods. Tolerations allow the scheduler to schedule pods with matching taints. Tolerations allow scheduling but don't guarantee scheduling: the scheduler also evaluates other parameters as part of its function. Taints and tolerations work together to ensure that pods are not scheduled onto inappropriate nodes. One or more taints are applied to a node; this marks that the node should"

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/scheduling-eviction/taint-and-toleration#c0` (`Taints and Tolerations`)
  > "Node affinity is a property of Pods that attracts them to a set of nodes (either as a preference or a hard requirement). Taints are the opposite -- they allow a node to repel a set of pods. Tolerations are applied to pods. Tolerations allow the scheduler to schedule pods with matching taints. Tolerations allow scheduling but don't guarantee scheduling: the scheduler also evaluates other parameters as part of its function. Taints and tolerations work together to ensure that pods are not scheduled onto inappropriate nodes. One or more taints are applied to a node; this marks that the node should"

---

## Q-039: How do I scale a Deployment with kubectl?
- **Type**: `procedural`
- **Status**: `yes`
- **Gold Docs**: `['concepts/workloads/controllers/deployment']`
- **Must Include**: `['kubectl scale', '--replicas']`
- **Expected Answer**: You scale a Deployment with the command: kubectl scale deployment/<deployment-name> --replicas=<count>.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/workloads/controllers/deployment#c10` (`Deployments > Scaling a Deployment`)
  > "You can scale a Deployment by using the following command:  ```shell kubectl scale deployment/nginx-deployment --replicas=10 ```  The output is similar to this:  ``` deployment.apps/nginx-deployment scaled ```  Assuming horizontal Pod autoscaling is enabled in your cluster, you can set up an autoscaler for your Deployment and choose the minimum and maximum number of Pods you want to run based on the CPU utilization of your existing Pods.  ```shell kubectl autoscale deployment/nginx-deployment --min=10 --max=15 --cpu-percent=80 ```  The output is similar to this:  ``` deployment.apps/nginx-depl"

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/controllers/deployment#c10` (`Deployments > Scaling a Deployment`)
  > "You can scale a Deployment by using the following command:  ```shell kubectl scale deployment/nginx-deployment --replicas=10 ```  The output is similar to this:  ``` deployment.apps/nginx-deployment scaled ```  Assuming horizontal Pod autoscaling is enabled in your cluster, you can set up an autoscaler for your Deployment and choose the minimum and maximum number of Pods you want to run based on the CPU utilization of your existing Pods.  ```shell kubectl autoscale deployment/nginx-deployment --min=10 --max=15 --cpu-percent=80 ```  The output is similar to this:  ``` deployment.apps/nginx-depl"

---

## Q-040: What are the QoS classes of a Pod and how is each one assigned?
- **Type**: `multi_chunk`
- **Status**: `yes`
- **Gold Docs**: `['tasks/configure-pod-container/quality-service-pod']`
- **Must Include**: `['Guaranteed', 'Burstable', 'BestEffort']`
- **Expected Answer**: The QoS classes are Guaranteed (every container has CPU and memory requests equal to limits), Burstable (at least one container has requests set and criteria for Guaranteed are not met), and BestEffort (no containers have memory or CPU requests or limits).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:tasks/configure-pod-container/quality-service-pod#c0` (`Configure Quality of Service for Pods`)
  > "This page shows how to configure Pods so that they will be assigned particular Quality of Service (QoS) classes. Kubernetes uses QoS classes to make decisions about evicting Pods when Node resources are exceeded. When Kubernetes creates a Pod it assigns one of these QoS classes to the Pod: Guaranteed Burstable * BestEffort"

- **Chunk ID**: `v1.27:tasks/configure-pod-container/quality-service-pod#c3` (`Configure Quality of Service for Pods > Create a Pod that gets assigned a QoS class of Guaranteed`)
  > "For a Pod to be given a QoS class of Guaranteed: Every Container in the Pod must have a memory limit and a memory request. For every Container in the Pod, the memory limit must equal the memory request. Every Container in the Pod must have a CPU limit and a CPU request. For every Container in the Pod, the CPU limit must equal the CPU request. These restrictions apply to init containers and app containers equally. Ephemeral containers cannot define resources so these restrictions do not apply. Here is a manifest for a Pod that has one Container. The Container has a memory limit and a memory req"

- **Chunk ID**: `v1.27:tasks/configure-pod-container/quality-service-pod#c5` (`Configure Quality of Service for Pods > Create a Pod that gets assigned a QoS class of Burstable`)
  > "A Pod is given a QoS class of Burstable if: The Pod does not meet the criteria for QoS class Guaranteed. At least one Container in the Pod has a memory or CPU request or limit. Here is a manifest for a Pod that has one Container. The Container has a memory limit of 200 MiB and a memory request of 100 MiB.  ```yaml apiVersion: v1 kind: Pod metadata:   name: qos-demo-2   namespace: qos-example spec:   containers:   - name: qos-demo-2-ctr     image: nginx     resources:       limits:         memory: "200Mi"       requests:         memory: "100Mi" ```  Create the Pod:  ```shell kubectl apply -f ht"

#### Version 1.31
- **Chunk ID**: `v1.31:tasks/configure-pod-container/quality-service-pod#c0` (`Configure Quality of Service for Pods`)
  > "This page shows how to configure Pods so that they will be assigned particular Quality of Service (QoS) classes. Kubernetes uses QoS classes to make decisions about evicting Pods when Node resources are exceeded. When Kubernetes creates a Pod it assigns one of these QoS classes to the Pod: Guaranteed Burstable * BestEffort"

- **Chunk ID**: `v1.31:tasks/configure-pod-container/quality-service-pod#c3` (`Configure Quality of Service for Pods > Create a Pod that gets assigned a QoS class of Guaranteed`)
  > "For a Pod to be given a QoS class of Guaranteed: Every Container in the Pod must have a memory limit and a memory request. For every Container in the Pod, the memory limit must equal the memory request. Every Container in the Pod must have a CPU limit and a CPU request. For every Container in the Pod, the CPU limit must equal the CPU request. These restrictions apply to init containers and app containers equally. Ephemeral containers cannot define resources so these restrictions do not apply. Here is a manifest for a Pod that has one Container. The Container has a memory limit and a memory req"

- **Chunk ID**: `v1.31:tasks/configure-pod-container/quality-service-pod#c5` (`Configure Quality of Service for Pods > Create a Pod that gets assigned a QoS class of Burstable`)
  > "A Pod is given a QoS class of Burstable if: The Pod does not meet the criteria for QoS class Guaranteed. At least one Container in the Pod has a memory or CPU request or limit. Here is a manifest for a Pod that has one Container. The Container has a memory limit of 200 MiB and a memory request of 100 MiB.  ```yaml apiVersion: v1 kind: Pod metadata:   name: qos-demo-2   namespace: qos-example spec:   containers:   - name: qos-demo-2-ctr     image: nginx     resources:       limits:         memory: "200Mi"       requests:         memory: "100Mi" ```  Create the Pod:  ```shell kubectl apply -f ht"

---

## Q-041: What are the possible Pod phases?
- **Type**: `table_or_code`
- **Status**: `yes`
- **Gold Docs**: `['concepts/workloads/pods/pod-lifecycle']`
- **Must Include**: `['Pending', 'Running', 'Succeeded', 'Failed']`
- **Expected Answer**: The possible Pod phases are Pending, Running, Succeeded, Failed, and Unknown.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/workloads/pods/pod-lifecycle#c1` (`Pod Lifecycle > Pod lifetime`)
  > "Like individual application containers, Pods are considered to be relatively ephemeral (rather than durable) entities. Pods are created, assigned a unique ID (UID), and scheduled to nodes where they remain until termination (according to restart policy) or deletion. If a Node dies, the Pods scheduled to that node are scheduled for deletion after a timeout period. Pods do not, by themselves, self-heal. If a Pod is scheduled to a node that then fails, the Pod is deleted; likewise, a Pod won't survive an eviction due to a lack of resources or Node maintenance. Kubernetes uses a higher-level abstr"

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/pods/pod-lifecycle#c1` (`Pod Lifecycle > Pod lifetime`)
  > "Whilst a Pod is running, the kubelet is able to restart containers to handle some kind of faults. Within a Pod, Kubernetes tracks different container states and determines what action to take to make the Pod healthy again. In the Kubernetes API, Pods have both a specification and an actual status. The status for a Pod object consists of a set of Pod conditions. You can also inject custom readiness information into the condition data for a Pod, if that is useful to your application. Pods are only scheduled once in their lifetime; assigning a Pod to a specific node is called binding, and the pro"

---

## Q-042: What does a PodDisruptionBudget do and which fields does it use?
- **Type**: `multi_chunk`
- **Status**: `yes`
- **Gold Docs**: `['concepts/workloads/pods/disruptions']`
- **Must Include**: `['minAvailable', 'maxUnavailable']`
- **Expected Answer**: A PodDisruptionBudget limits voluntary disruptions to an application by specifying either minAvailable (minimum number or percentage of pods that must be available) or maxUnavailable (maximum number or percentage of pods that can be unavailable).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/workloads/pods/disruptions#c3` (`Disruptions > Pod disruption budgets`)
  > "FEATURE STATE: Kubernetes v1.21 [stable] Kubernetes offers features to help you run highly available applications even when you introduce frequent voluntary disruptions. As an application owner, you can create a PodDisruptionBudget (PDB) for each application. A PDB limits the number of Pods of a replicated application that are down simultaneously from voluntary disruptions. For example, a quorum-based application would like to ensure that the number of replicas running is never brought below the number needed for a quorum. A web front end might want to ensure that the number of replicas servin"

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/pods/disruptions#c3` (`Disruptions > Pod disruption budgets`)
  > "FEATURE STATE: Kubernetes v1.21 [stable] Kubernetes offers features to help you run highly available applications even when you introduce frequent voluntary disruptions. As an application owner, you can create a PodDisruptionBudget (PDB) for each application. A PDB limits the number of Pods of a replicated application that are down simultaneously from voluntary disruptions. For example, a quorum-based application would like to ensure that the number of replicas running is never brought below the number needed for a quorum. A web front end might want to ensure that the number of replicas servin"

---

## Q-043: How do I set CPU and memory requests and limits for a container?
- **Type**: `procedural`
- **Status**: `yes`
- **Gold Docs**: `['tasks/configure-pod-container/assign-memory-resource', 'tasks/configure-pod-container/assign-cpu-resource']`
- **Must Include**: `['resources', 'requests', 'limits']`
- **Expected Answer**: In the container spec under resources, configure requests and limits specifying CPU and memory values (for example resources.requests.memory, resources.limits.memory, resources.requests.cpu, resources.limits.cpu).

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:tasks/configure-pod-container/assign-memory-resource#c3` (`Assign Memory Resources to Containers and Pods > Specify a memory request and a memory limit`)
  > "To specify a memory request for a Container, include the resources:requests field in the Container's resource manifest. To specify a memory limit, include resources:limits. In this exercise, you create a Pod that has one Container. The Container has a memory request of 100 MiB and a memory limit of 200 MiB. Here's the configuration file for the Pod:  ```yaml apiVersion: v1 kind: Pod metadata:   name: memory-demo   namespace: mem-example spec:   containers:   - name: memory-demo-ctr     image: polinux/stress     resources:       requests:         memory: "100Mi"       limits:         memory: "2"

#### Version 1.31
- **Chunk ID**: `v1.31:tasks/configure-pod-container/assign-memory-resource#c3` (`Assign Memory Resources to Containers and Pods > Specify a memory request and a memory limit`)
  > "To specify a memory request for a Container, include the resources:requests field in the Container's resource manifest. To specify a memory limit, include resources:limits. In this exercise, you create a Pod that has one Container. The Container has a memory request of 100 MiB and a memory limit of 200 MiB. Here's the configuration file for the Pod:  ```yaml apiVersion: v1 kind: Pod metadata:   name: memory-demo   namespace: mem-example spec:   containers:   - name: memory-demo-ctr     image: polinux/stress     resources:       requests:         memory: "100Mi"       limits:         memory: "2"

---

## Q-044: How does a Job track completions and what does parallelism control?
- **Type**: `multi_chunk`
- **Status**: `yes`
- **Gold Docs**: `['concepts/workloads/controllers/job']`
- **Must Include**: `['completions', 'parallelism']`
- **Expected Answer**: A Job uses .spec.completions to specify the number of successful Pod completions required to complete the Job, while .spec.parallelism sets the maximum number of Pods that can run concurrently.

### Verbatim Evidence from Corpus Chunks

#### Version 1.27
- **Chunk ID**: `v1.27:concepts/workloads/controllers/job#c6` (`Jobs > Writing a Job spec > Parallel execution for Jobs`)
  > "There are three main types of task suitable to run as a Job: 1. Non-parallel Jobs - normally, only one Pod is started, unless the Pod fails. - the Job is complete as soon as its Pod terminates successfully. 1. Parallel Jobs with a fixed completion count: - specify a non-zero positive value for .spec.completions. - the Job represents the overall task, and is complete when there are .spec.completions successful Pods. - when using .spec.completionMode="Indexed", each Pod gets a different index in the range 0 to .spec.completions-1. 1. Parallel Jobs with a work queue: - do not specify .spec.comple"

#### Version 1.31
- **Chunk ID**: `v1.31:concepts/workloads/controllers/job#c6` (`Jobs > Writing a Job spec > Parallel execution for Jobs`)
  > "There are three main types of task suitable to run as a Job: 1. Non-parallel Jobs - normally, only one Pod is started, unless the Pod fails. - the Job is complete as soon as its Pod terminates successfully. 1. Parallel Jobs with a fixed completion count: - specify a non-zero positive value for .spec.completions. - the Job represents the overall task, and is complete when there are .spec.completions successful Pods. - when using .spec.completionMode="Indexed", each Pod gets a different index in the range 0 to .spec.completions-1. 1. Parallel Jobs with a work queue: - do not specify .spec.comple"

---

