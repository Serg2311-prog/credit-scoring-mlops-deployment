# credit-scoring-mlops-deployment

Промышленное развертывание кредитной скоринговой системы с полным MLOps-циклом (учебный итоговый проект).

**Текущий статус:** завершён только этап 0 — аудит исходного проекта и проектирование.  
Реализация этапов 1–7 не начата.

Исходный ML-проект: [credit-default-prediction](https://github.com/Serg2311-prog/credit-default-prediction).

## Документы этапа 0

- [План реализации и архитектура](docs/implementation_plan.md)
- [Матрица требований и критерии проверки](docs/requirements_matrix.md)
- [Черновик архитектурной диаграммы](docs/architecture/overview.md)

## Baseline (не изменять без реального переобучения)

RandomForestClassifier из исходного проекта:

- CV ROC-AUC: 0.7837
- Test ROC-AUC: 0.7771
- PR-AUC: 0.5536
- Precision: 0.4786
- Recall: 0.6081
- F1: 0.5357
- Accuracy: 0.7668

## Быстрая проверка артефактов этапа 0

```powershell
cd "C:\Users\Sergey\Documents\Личное\Учеба\3 Семестр\Автоматизация процессов доставки и развертывания ML-моделей\ИТОГОВЫЙ ПРОЕКТ\credit-scoring-mlops-deployment"
Get-ChildItem docs -Recurse -File
Test-Path docs\implementation_plan.md
Test-Path docs\requirements_matrix.md
```

После подтверждения будет начат **этап 1** (PyTorch NN → ONNX → quantization → CPU benchmarks).
