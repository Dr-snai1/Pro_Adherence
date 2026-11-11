# Stage 3 — закрытый census и preflight трёх линз (PLANNING ONLY)

**Единственный текущий статус проекта:** [07_STAGE_STATUS](https://docs.google.com/document/d/1GhQfnsbxK8lilvpnZqWeFu99w67DwWKJmY5OTthxvhM/edit). Это технический план воспроизводимости, **не разрешение** на inference, загрузку больших моделей, оплату GPU, публикацию/merge или переход Stage.

## 1. Зафиксированная аналитическая популяция — получена и сохранена

- Immutable input: restricted Stage2 ZIP SHA256 `a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127`; 87 511 исходных записей / 57 293 канонические группы.
- Утверждённая private основная выборка: **57 204** primary eligible; **86** book-only excluded и **3** confirmed retraction excluded. **19** APA peer-review-unknown и **413** WoS NR/CR mismatch сохраняются включёнными с диагностическими флагами. Пересечений этих особых категорий / mixed book+journal в принятом корпусе не обнаружено.
- **Полный приватный реестр (57 293 строк):** `article_eligibility_stage3_private.jsonl.gz`; 3 243 863 bytes, SHA256 `c080449e4a3450e6ff2e396c0463d05960d8b1cd101f42c7f99ccf3ab202e234`. Приватный Drive URL и права хранит текущий закрытый статус проекта, не публичный репозиторий.
- **Приватная сводка**: `eligibility_summary_stage3_private.json`, SHA256 `20a01d4a63976f5db19b3ecf0d336faf2461fe88d830a2a5c6aed56358fbd433`.
- Оба файла находятся в исходной restricted project folder в Google Drive. Метаданные подтверждают `shared=false` и доступ только владельцу; по повторному скачиванию совпадают точные byte SHA256. Для реестра независимо перепроверены gzip parse, 57 293 row count и 57 204 eligible. Приватные Drive file/folder IDs не дублируются в публичных рабочих инструкциях.
- Deterministic offline producer: `scripts/stage3_eligibility_census.py` (frozen Stage2 ZIP hash+ZIP CRC, полный source→canonical coverage, explicit source flag exposure vs `not_exposed`, вторая проверка со Stage2 `article_only_eligible`, `gzip(mtime=0)` и versioned restricted derived manifest). Запускать только в закрытом окружении, **производные строки/идентификаторы не помещать в публичный GitHub**.

## 2. Точные версии upstream: зафиксированы как кандидаты для загрузки (не как уже проверенные модельные байты)

| Линза | Репозиторий | Full HF commit SHA |
|---|---|---|
| PubMedBERT CLS+Mean | `microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract` | `d673b8835373c6fa116d6d8006b33d48734e305d` |
| SPECTER2 Base | `allenai/specter2_base` | `3447645e1def9117997203454fa4495937bfbd83` |
| SPECTER2 proximity adapter | `allenai/specter2` | `2081559630a80fc5851d8f798a05ba81e9468089` |

Список обязательных файлов и ссылки на verified public commit pages: `configs/stage3/model_preflight_pins.json`. Указанные full commit SHAs **не равны** SHA256 скачанных бинарных весов. Веса ещё НЕ скачаны и их file-level SHA256 ещё НЕ подтверждены. Нельзя объявлять `model_identity_hash` готовым по одному только адресу репозитория или короткому SHA.

## 3. ML runtime: подтверждённая несовместимость (не новый научный выбор)

Исходный [AdapterHub setup.py v1.3.0](https://github.com/adapter-hub/adapters/blob/v1.3.0/setup.py) требует transformers~=4.57.6 (то есть >=4.57.6,<4.58.0). Для transformers действует [GHSA-29pf-2h5f-8g72](https://github.com/advisories/GHSA-29pf-2h5f-8g72): исправление — начиная с 5.3.0. **Пересечение диапазонов пусто.** Это риск технической совместимости и безопасности среды, а не основание менять утверждённый SPECTER2 proximity adapter.

No-download аудит: PYTHONPATH=src python -m pro_adherence.stage3_runtime_guard --adapters 1.3.0 --transformers 5.3.0 возвращает BLOCKED по несовместимости. С transformers=4.57.6 он возвращает BLOCKED по security-floor. Пока не проверены фактические dependency metadata иной совместимой версии/патча и реальный adapter smoke, **нет подтверждённого безопасного exact ML runtime lock для SPECTER2**. Не создавать фиктивный lock/SHA и не устанавливать заведомо уязвимую пару. PubMedBERT и node2vec могут использовать отдельные среды, но exact wheel hashes и smoke ещё не проверены.

HF full revisions остаются закреплены; **file-level model SHA256, provider metadata digests, независимые hashes полученных весов и model_identity_hash — PENDING**. SHA коммита Git не является SHA256 бинарных весов. Весовые файлы не загружались.

## 4. Строго блокирующие условия перед отдельным разрешённым compute

1. **Weights/tokenizer/adapter:** получить только выбранные полные HF revisions, установить проверенные авторитетные file SHA256 по official artifact metadata и независимо сравнить с фактически полученными bytes. Обязательные `config.json`, tokenizer files, `pytorch_model.bin` / `pytorch_adapter.bin` должны проверяться отдельно.
2. **Runtime:** зафиксировать *отдельный* совместимый dependency lock для модельных вычислений (PyTorch, transformers, tokenizers и adapters для SPECTER2; node2vec backend), версии Python/GPU/CPU и hashes. Действующий Stage0 lock **не содержит** этих ML-библиотек и не считается готовым ML runtime. Совместимость SPECTER2 adapter проверяется в целевом runtime техническим smoke test — не открывать научную развилку.
3. **Node2vec graph:** на approved primary_eligible cohort `57 204` получить sorted canonical-to-node mapping + hash, immutable directed observed graph + hash, separate binary unweighted undirected graph + hash, isolate/coverage report; воспроизводимо сверить отсечение excluded и self-loops без потери исходных цитирований. Граф и trained node2vec identity пока НЕ созданы.
4. **Numerical and quality checks:** только после отдельного решения о вычислениях валидировать размерности 768/128, pooled/text policies, raw/norm/unit, cosine, null statuses, SPECTER2 token loss; у node2vec проверить reproducible walks/seed без навязанного поиска новых гиперпараметров.
5. **Owner gate:** отдельно утвердить параметры пилота, финансовый потолок и фактический запуск. Никакой локальный PASS по статическим файлам не считается таким разрешением.

## 5. Node2vec graph: restricted frozen input materialized and verified

**Граф ПОЛУЧЕН 2026-11-11** из точного frozen Stage2 research ZIP и private derived eligibility roster. Этот ZIP содержит поля citation links resolution / target_canonical_article_id / reference_ordinal, отличающиеся от GitHub one-shot schema; поэтому для настоящего frozen входа использовался **scripts/stage3_graph_frozen_streaming.py** (SQLite streaming, полная source→canonical и raw reference SHA/ordinal проверка), а не synthetic/staging helper scripts/stage3_graph_snapshot.py. Научная политика уже зафиксирована и не изменялась.

- Source input: **87 511** records, **57 293** canonical, **57 204** eligible; 2 437 863 references = **406 811** exact DOI, **223** ambiguous, **2 030 829** unresolved. Все 223 ambiguous не получают целей.
- Directed original graph: **328 383** уникальных направленных пар из 406 811 exact DOI observations, включая evidence исключённых и self-citations. Отдельный private источник сохранённых provenance: **406 811** source/ordinal/raw-export-SHA pointers.
- Eligible node2vec projection: **328 298** уникальных ненаправленных пар с weight=1, **406 729** наблюдений; 50 исключены по eligible endpoints, 32 — по self-loop (в training, **не** в original evidence). В approved eligible roster **13 596** вершин без разрешённого ребра; их vector status при обучении — missing_structural/null, не fake-zero.
- Immutable private ZIP **23 826 946 bytes**, SHA256 **33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c**. Внутри четыре deterministic gzip output плюс manifest. Manifest SHA256 **478b29cb00d837d50c3eda24d92251f2753a9fe976f02197da1f925d2fab5bd4**. Exact Drive IDs, ACL и доступ хранятся в restricted project root/рабочем учёте, не в публичном GitHub.
- Проверки **разными механизмами**: streaming input reconciliation по source references/canonical/eligibility; альтернативный полный gzip+graph-invariants scan; независимый второй прогон дал **0 byte differences**; после upload на Google Drive — отдельное скачивание и SHA256 ZIP, ZIP CRC, gzip row-count/digests; ACL owner-only/shared=false, родитель project root подтверждён.
- Граф — **derived non-model artifact**, не trained node2vec model и не grant compute. Runtime, HF model file SHA/weights, trained-model identity и owner compute permission остаются PENDING. Node2vec training **НЕ** запускался.

Ресурсная нижняя оценка будущего training: 57 204 × 10 × 40 = **22 881 600** nominal walk steps; raw float32 128d = **29 288 448 bytes**, raw+unit = **58 576 896 bytes**, без служебных массивов и peak RAM. Это не measured throughput, memory peak или GPU cost. Нужен отдельный разрешённый pilot benchmark; граф уже подготовлен без heavy training.


## 6. Автоматический offline preflight

```bash
PYTHONPATH=src python -m pro_adherence.stage3_preflight \
  --config configs/stage3/model_preflight_pins.json

# Ожидается FAIL-CLOSED: для всех линз пока есть blockers.
PYTHONPATH=src python -m pro_adherence.stage3_preflight \
  --config configs/stage3/model_preflight_pins.json --require-ready
# exit code 2, пока отсутствуют необходимые внешние подтверждения.
```

`src/pro_adherence/stage3_preflight.py` теперь различает approved pins и НЕ проверенные upstream provider metadata (поле upstream_commit_refs_verified=false), требует действительные байты runtime lock и трёх файлов графа при заявлении SHA, проверяет известный конфликт adapters/transformers; данные из одной лишь строки digest не проходят готовность. `src/pro_adherence/stage3_preflight.py` проверяет точные репозитории/full commits, frozen cohort SHA и запрет публикации, локальные SHA файла против **внешних доверенных SHA**, exact runtime lock, node2vec graph hashes и отдельный compute gate. Он не вызывает Hugging Face API, не загружает/не исполняет веса и не читает скрыто приватный корпус без явного пути. Синтетические тесты проверяют отказ при подмене модели, адаптера, cohort, файла/контрольной суммы, graph policy или Stage-gate. Автоматический CI ограничен синтетическими данными.

**Статус:** закрытый census — VERIFIED_AND_STORED; публичные full revision refs — PINNED; фактические модели/runtime/graph — **PENDING**; heavy compute / publication / Stage transition — **NOT_AUTHORIZED**.
