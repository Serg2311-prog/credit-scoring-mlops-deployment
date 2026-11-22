# credit-scoring-mlops-deployment

Промышленное развертывание кредитной скоринговой системы с полным MLOps-циклом (учебный итоговый проект).

**Текущий статус:** этап 0 (архитектура) и **этап 1 (NN → ONNX → quant → CPU benchmarks)** завершены.  
Этапы 2–7 не начаты.

Исходный ML-проект: [credit-default-prediction](https://github.com/Serg2311-prog/credit-default-prediction).

## Документы

- [План реализации](docs/implementation_plan.md)
- [Матрица требований](docs/requirements_matrix.md)
- [Benchmark-отчёт этапа 1](docs/model_benchmark.md)
- [Аудит этапа 1](docs/stage1_audit_report.md)
- [Архитектура](docs/architecture/overview.md)

## Baseline Random Forest (неизменяемый без переобучения)

| Метрика | Значение |
| --- | ---: |
| CV ROC-AUC | 0.7837 |
| Test ROC-AUC | 0.7771 |
| PR-AUC | 0.5536 |
| Precision | 0.4786 |
| Recall | 0.6081 |
| F1 | 0.5357 |
| Accuracy | 0.7668 |

## MLP (измеренный прогон этапа 1)

| Метрика test | Значение |
| --- | ---: |
| ROC-AUC | 0.7742 |
| PR-AUC | 0.5509 |
| Precision | 0.4375 |
| Recall | 0.6307 |
| F1 | 0.5167 |
| Accuracy | 0.7390 |

MLP уступает RF по ROC-AUC/F1 — зафиксировано честно. Для NN-serving рекомендуется **ONNX FP32**.

## Воспроизведение этапа 1 (PowerShell)

```powershell
cd "C:\Users\Sergey\Documents\Личное\Учеба\3 Семестр\Автоматизация процессов доставки и развертывания ML-моделей\ИТОГОВЫЙ ПРОЕКТ\credit-scoring-mlops-deployment"

# Нужен data\raw\UCI_Credit_Card.csv
C:\Users\Sergey\AppData\Local\Programs\Python\Python313\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt -r requirements-nn.txt

python -m src.data.make_dataset
python -m src.nn.train_nn
python -m src.nn.export_onnx
python -m src.nn.parity
python -m src.nn.quantize
python -m src.nn.benchmark --device cpu
python -m src.nn.benchmark --device cuda   # SKIPPED без GPU

pytest -v
flake8 src tests
black --check src tests
```

Либо: `.\scripts\run_stage1.ps1`

## Примечание по Python

На машине разработки фактически доступен Python **3.13**. Требование учебного ТЗ — 3.11; при появлении 3.11 достаточно пересоздать `.venv`.
