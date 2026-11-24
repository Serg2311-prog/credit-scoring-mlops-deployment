# Optional GPU workload scheduling (example only)

Default serving (API/frontend) runs on **CPU** node groups and needs no GPU.

When Terraform `enable_gpu_node_group=true` (cloud apply — **NOT_EXECUTED** here),
GPU nodes get:

- labels: `workload.credit-scoring/type=gpu`, `nvidia.com/gpu=true`
- taints: `nvidia.com/gpu=true:NoSchedule`, `workload.credit-scoring/gpu=true:NoSchedule`

`deployment-gpu-example.yaml` includes:

- `nodeSelector` → GPU label
- `tolerations` matching Terraform `node_taints`
- `resources.limits/requests: nvidia.com/gpu: 1`

**Still required in a real Yandex MK8s GPU cluster (NOT_EXECUTED / needs cloud verification):**

- GPU platform availability in the chosen zone (`gpu-standard-v3` or current YC SKU)
- `gpu_settings.gpu_environment` matching node image (`runc_drivers_cuda` vs `runc`)
- NVIDIA device plugin / GPU operator so `nvidia.com/gpu` is allocatable
- Driver/CUDA stack compatible with the workload image

Do **not** apply this example on the local kind laptop cluster.
