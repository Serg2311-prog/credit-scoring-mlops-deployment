"""Экспорт обученной MLP в ONNX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import torch

from src.config import dump_json, load_params, nn_onnx_path, artifacts_dir
from src.nn.runtime import configure_cpu_threads, load_checkpoint


def export_onnx(
    checkpoint: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    configure_cpu_threads()
    params = load_params()
    onnx_params = params.get("onnx", {})
    opset = int(onnx_params.get("opset", 17))
    use_dynamic = bool(onnx_params.get("dynamic_axes", True))

    model, payload = load_checkpoint(checkpoint, map_location="cpu")
    model.eval()
    input_dim = int(payload.get("input_dim") or model.input_dim)
    destination = output or nn_onnx_path()
    destination.parent.mkdir(parents=True, exist_ok=True)

    dummy = torch.zeros((1, input_dim), dtype=torch.float32)
    dynamic_axes = None
    if use_dynamic:
        dynamic_axes = {"features": {0: "batch"}, "logits": {0: "batch"}}

    # dynamo=False: стабильный legacy exporter для компактной MLP на CPU.
    torch.onnx.export(
        model,
        dummy,
        str(destination),
        export_params=True,
        opset_version=opset,
        do_constant_folding=True,
        input_names=["features"],
        output_names=["logits"],
        dynamic_axes=dynamic_axes,
        dynamo=False,
    )

    # Базовая проверка загрузки ORT
    import onnx
    import onnxruntime as ort

    onnx_model = onnx.load(str(destination))
    onnx.checker.check_model(onnx_model)
    session = ort.InferenceSession(
        str(destination),
        providers=["CPUExecutionProvider"],
    )
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    probe = np.zeros((1, input_dim), dtype=np.float32)
    ort_out = session.run(None, {inputs[0].name: probe})[0]

    report = {
        "onnx_path": str(destination),
        "opset": opset,
        "dynamic_axes": use_dynamic,
        "input_name": inputs[0].name,
        "input_shape": list(inputs[0].shape),
        "output_name": outputs[0].name,
        "output_shape": list(outputs[0].shape),
        "input_dim": input_dim,
        "file_size_bytes": destination.stat().st_size,
        "ort_providers": session.get_providers(),
        "ort_probe_logits_shape": list(np.asarray(ort_out).shape),
        "model_config": payload.get("model_config"),
    }
    dump_json(artifacts_dir() / "onnx_export.json", report)
    print(f"ONNX сохранён: {destination}")
    print(f"Размер: {report['file_size_bytes']} байт")
    print(f"Вход: {report['input_name']} {report['input_shape']}")
    print(f"Выход: {report['output_name']} {report['output_shape']}")
    return report


def main() -> None:
    export_onnx()


if __name__ == "__main__":
    main()
