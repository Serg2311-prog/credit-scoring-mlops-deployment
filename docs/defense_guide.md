# Подготовка к защите

## Краткое описание

Учебный MLOps-проект кредитного скоринга: MLP → ONNX FP32 API → Docker/kind → Terraform (`cloud-experiment` apply→destroy, Block 11) → GitHub Actions → Prometheus/Loki → Evidently drift + A/B → Airflow retraining без auto-promote. Cloud app — `ABORT_CLOUD_APP`. Holdout MLP ROC-AUC **0.7742** ниже RF baseline **0.7771** — зафиксировано честно.

---

## Демонстрация 7–10 минут

| Мин | Шаг |
| ---: | --- |
| 0:00–1:00 | Задача + архитектура (Mermaid overview) |
| 1:00–2:30 | Метрики: RF vs MLP vs ONNX; почему FP32 champion |
| 2:30–3:30 | API `/health/ready` + `/docs` или Compose UI |
| 3:30–4:30 | CI: 5 gates + Trivy (Actions / cicd_pipeline.md) |
| 4:30–6:00 | Monitoring: Grafana + пример alert evidence Block 8 |
| 6:00–7:30 | Drift demo CLI / concept experiment caveat + online A/B JSON |
| 7:30–8:30 | Airflow: trigger → candidate, `auto_promote=false` |
| 8:30–9:30 | Terraform: Block 11 apply→destroy + validate staging/prod |
| 9:30–10:00 | Ограничения + вопросы |

**Последовательность стенда (8 GB):** тесты → API **или** Compose → (опционально) observability **после** `down` inference-only при нехватке RAM. Не поднимать Airflow параллельно.

---

## Ключевые технические решения

1. **ONNX FP32 CPU** как production serving: parity с PyTorch, стабильные вероятности, меньше риск INT8 drift решений.
2. **Quantization** — отдельный experimental артефакт и online A/B challenger, не silent replace.
3. **IaC** — модульный Terraform; Block 11 `cloud-experiment` apply→destroy; staging/prod без apply.
4. **Observability** — metrics + logs alerts с firing/resolved evidence.
5. **Retraining** — decision layer + candidate artifacts; registry immutable без явного promote.

## Почему ONNX FP32 CPU

- Holdout quality идентичен PyTorch (0.7742).
- Runtime image без Torch/CUDA.
- Quant меняет scores/решения → небезопасен как неявный champion.
- GPU T4 измерен для latency comparison, но целевой прод-контур курса — CPU serving.

## GPU benchmark

- Tesla T4 Colab hardened: `results/block7/colab/hardened/`.
- Не смешивать с holdout quality.
- GPU INT8 / GPU HTTP — не выполнялись.

## Quantization

- Dynamic INT8: меньше файл, ROC-AUC ≈0.7732 (ORT 1.32.0), смена решений ~1.25%; исторические 0.7720/0.7736 — другие ORT-снимки.
- Используется как A/B challenger в изолированном окружении.

## Monitoring и drift

- Data drift = Evidently feature distribution.
- Degradation = labeled metric drop signal.
- Concept drift в prod не доказывается только AUC; synthetic P(Y|X) experiment — controlled lab.

## A/B и retraining

- Online A/B: hash assignment, weights, dual ONNX, metrics per group.
- Airflow: drift/quality/new_data → retrain candidate; **auto_promote=false**.

---

## 20 вероятных вопросов и ответы

1. **Почему MLP хуже RF?**
   Holdout: RF 0.7771 vs MLP 0.7742. NN нужна для ONNX/serving/MLOps-контура; качество не приукрашиваем.

2. **Что в production?**
   ONNX FP32 + preprocessor; registry указывает champion; AB выключен.

3. **Зачем quant, если не лучше?**
   Размер/latency эксперименты и A/B challenger; не silent replace.

4. **Почему не apply Terraform?**
   Политика курса/стоимость; код + validate достаточны; apply — отдельное решение.

5. **Есть ли remote state?**
   Examples есть; live bucket/state **не** создавались.

6. **Как доказан CI?**
   GitHub Actions workflows SUCCESS (python/docker/infra/k8s/airflow + orchestrator).

7. **Что сканирует Trivy?**
   Образы в `ci-docker`; gate не ослаблялся.

8. **Как устроен log alert?**
   Alloy → Loki → Ruler LogQL → Alertmanager → webhook; evidence firing/resolved.

9. **Почему probe не в API?**
   Security: test-only `e2e-log-probe` в E2E overlay.

10. **Что такое concept drift у вас?**
    Изменение P(Y|X). Production claim только с label-relation evidence; иначе degradation signal / controlled synthetic.

11. **Online A/B на реальных клиентах?**
    Нет — synthetic HTTP в изолированном compose.

12. **Почему quant challenger?**
    Совместимый контракт, без retrain production; явно experimental INT8.

13. **Может ли Airflow затереть champion?**
    Нет при `auto_promote=false`; кандидаты в run dir.

14. **DVC в API image?**
    Нет; отдельный `Dockerfile.dvcdata`.

15. **NetworkPolicy работает?**
    Манифесты есть; runtime enforcement на kindnet не подтверждён.

16. **GPU в Yandex?**
    Node group в TF optional/default off; не запускалась.

17. **cAdvisor labels?**
    На Docker Desktop часто только cgroup `id`, без `name`.

18. **PII в репозитории?**
    Нет клиентских PII; evidence sanitized; backups gitignored.

19. **Как воспроизвести без GPU?**
    CPU tests + Compose + Block7/8 JSON evidence + Colab artifacts read-only.

20. **Что бы сделали в банке дальше?**
    Apply staging с budget, CALICO NP E2E, canary с отдельным challenger train, managed Airflow, cloud notifications — вне текущего verified scope.

---

## Ограничения (говорить прямо)

**Block 11 CLOUD_INFRA:** Remote State + apply + MK8s v1.34.1 + Ready worker + Calico + Metrics Server — verified; **destroy verified**; SG migration (12 rules) done.
**CLOUD_APP:** `ABORT_CLOUD_APP` (GHCR login denied + residual API Trivy HIGH + timebox).
**Still open / not claimed:** cloud inference/HPA/NP enforcement/monitoring/rollback; production apply; GPU cloud nodes; GPU INT8/HTTP; kind NP enforcement; optional Seldon/Istio/Redis; Airflow only local Docker E2E.
Финальные отчёты: `results/block11/FINAL_*.md`.
