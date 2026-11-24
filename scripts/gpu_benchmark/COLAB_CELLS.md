# Colab cells for hardened runner re-validation

Upload `artifacts/block7/colab_gpu_benchmark_hardened.zip`.
Do not reinstall PyTorch. Do not install CPU `onnxruntime` over GPU.

## 1 Upload
```python
from google.colab import files
uploaded = files.upload()
```

## 2 Unpack
```python
import zipfile, os, shutil
from pathlib import Path
zip_name = next(k for k in uploaded if k.endswith('.zip'))
work = Path('/content/colab_gpu_benchmark')
if work.exists(): shutil.rmtree(work)
work.mkdir(parents=True)
with zipfile.ZipFile(zip_name) as zf: zf.extractall(work)
entries=list(work.iterdir())
if len(entries)==1 and entries[0].is_dir(): work=entries[0]
os.chdir(work)
print(Path.cwd(), sorted(p.name for p in Path('.').iterdir()))
```

## 3 Deps
```python
import importlib, subprocess, sys
try: importlib.import_module('numpy')
except ImportError:
    subprocess.check_call([sys.executable,'-m','pip','install','-q','numpy'])
```

## 4 CUDA check
```python
import torch, onnxruntime as ort
assert torch.cuda.is_available()
assert 'CUDAExecutionProvider' in ort.get_available_providers()
print(torch.__version__, torch.cuda.get_device_name(0), ort.__version__)
```

## 5 ORT CUDA smoke (fallback disabled)
```python
import numpy as np, onnxruntime as ort
so = ort.SessionOptions()
so.add_session_config_entry('session.disable_cpu_ep_fallback','1')
sess = ort.InferenceSession('models/credit_scoring_nn.onnx', sess_options=so, providers=['CUDAExecutionProvider'])
sess.disable_fallback()
assert sess.get_providers()[0]=='CUDAExecutionProvider'
y=sess.run(None,{sess.get_inputs()[0].name: np.random.randn(4,47).astype('float32')})[0]
print('ok', y.shape, sess.get_providers())
```

## 6 Full benchmark (mandatory GPU)
```python
!python run_benchmark.py --device-set all --require-gpu --warmup 20 --timed 100 --repeats 3 --batch-sizes 1,8,32,64,128
```

## 7 Table + download
```python
import json, pandas as pd
from pathlib import Path
from google.colab import files
rep=json.loads(Path('out/colab_gpu_benchmark.json').read_text())
assert rep.get('gpu_status')=='VERIFIED_GPU'
display(pd.DataFrame(rep['results']))
display(pd.DataFrame(rep['parity']))
print(rep.get('ort_cuda_profile'))
files.download('out/colab_gpu_benchmark.json')
files.download('out/colab_gpu_benchmark.csv')
```
