# Hardened GPU benchmark package (Block 7.3)

This directory is the **maintained** Colab/GPU runner.

Hardened Colab evidence is **`VERIFIED_GPU`** under
`results/block7/colab/hardened/`. Historical Block 7.2 numbers remain under
`results/block7/colab/` — **do not mix or overwrite either set**.

## Hardening vs historical runner

1. `session.disable_cpu_ep_fallback=1`
2. `sess.disable_fallback()`
3. Primary provider must be `CUDAExecutionProvider`
4. Structured Node-event profile parsing (`args.provider`)
5. `VERIFIED_GPU` only if all Node events are CUDA and none are CPU
6. Profiling uses a separate session (not mixed into latency timings)
7. IOBinding setup outside the timed loop
8. Explicit PyTorch H2D vs ORT host I/O semantics
9. Input shape/dtype/finite/SHA256/batch validation
10. Thread + GPU + library metadata
11. `weights_only=True` with fallback
12. ZIP paths via `Path.as_posix()`
13. `--require-gpu` non-zero exit on CUDA/profile/parity failure

## Local CPU smoke

```bash
# from scripts/gpu_benchmark after packaging data/models via package_zip stage,
# or point --root at a prepared package directory:
python package_zip.py
# extract and:
python run_benchmark.py --device-set cpu --warmup 2 --timed 5 --repeats 1
```

## Colab (already VERIFIED_GPU for Block 7.4)

Evidence: `results/block7/colab/hardened/`. Optional re-run:

```bash
python run_benchmark.py --device-set all --require-gpu --warmup 20 --timed 100 --repeats 3
```
