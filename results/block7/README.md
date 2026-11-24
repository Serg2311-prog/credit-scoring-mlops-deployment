# Block 7 benchmark evidence (Git-tracked)

Compact, anonymized machine-readable results from the Block 7 local run.
Source working copies may also exist under gitignored rtifacts/block7/.

| File | Contents |
| --- | --- |
| parity_summary.json | PyTorch vs ONNX FP32 parity |
| quality_fp32_vs_quant.json | Holdout metrics, confusion, size, class disagreement |
| cpu_benchmark_model_only.csv / .json | CPU latency/throughput/RSS |
| cpu_thread_probe.csv | Threads 1/2/4 at batch=32 |
| cpu_benchmark_e2e_highlight.json | end-to-end subset |
| pi_load_summary.json | Concurrency 1/2/4/8 local uvicorn |
| gpu_status.json | BLOCKED_NO_GPU |
|
un_metadata.json | Hardware/software/methodology |
| plot_*.png | Comparison charts |

**Not cloud/K8s proof.** Do not treat local uvicorn RPS as pod-limit capacity.
