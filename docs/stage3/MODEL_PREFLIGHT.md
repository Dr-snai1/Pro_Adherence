# Stage 3 — закрытый census и preflight трёх линз (SCOPED EXECUTION)

**Единственный формальный Stage:** [07_STAGE_STATUS](https://docs.google.com/document/d/1GhQfnsbxK8lilvpnZqWeFu99w67DwWKJmY5OTthxvhM/edit), Stage 3 OPEN / EXECUTION, не закрыт. После отдельного прямого разрешения владельца 2026-11-12 обе CPU-линии **PubMedBERT и node2vec COMPLETE / TECHNICALLY VERIFIED / PRIVATE STORED**. PubMedBERT: 57 204/57 204, 58 immutable ZIP; node2vec: 43 608 nonisolated 128d raw/norm/unit, 13 596 missing_structural null; полный independent source/vector audit + Drive byte readback PASS. SPECTER2 safe proximity runtime остаётся BLOCKED. Никакой Stage4, PR merge, public release или иной compute из этого не следует. Формальный 07_STAGE_STATUS редактирует только 00.

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

Список обязательных файлов и immutable upstream refs: `configs/stage3/model_preflight_pins.json`. Полные HF commit SHAs **не равны** SHA256 файлов. Для PubMedBERT принят exact weight bytes SHA и выполнен полный CPU run; для SPECTER2 **proximity adapter** pinned revision `2081559630a80fc5851d8f798a05ba81e9468089`, checkpoint SHA256 `5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a` (3 593 365 bytes) и `adapter_config.json` SHA256 `1065ad610a661c5169f05d81040fe14429d2cc7ecdf83ed654dca4a62aaf9a8c` **реально скачаны, SHA/ZIP CRC сверены в публичном CI и повторно независимо проверены локально**. Сами весовые байты и инспекционный отчёт сохранены в restricted owner-only Drive; **base SPECTER2 weight bytes и safe adapter-activated runtime не подтверждены**. Никакого SPECTER2 inference.

## 3. ML runtime: безопасные раздельные кандидаты, SPECTER2 BLOCKED

На 2026-11-11 последний опубликованный [Adapters 1.3.0](https://pypi.org/project/adapters/1.3.0/) требует `transformers~=4.57.6` (то есть >=4.57.6,<4.58.0) по [исходному setup.py](https://github.com/adapter-hub/adapters/blob/v1.3.0/setup.py). Официальные GHSA: версии `<5.3.0` [29pf](https://github.com/advisories/GHSA-29pf-2h5f-8g72), `<5.5.0` [fgcw](https://github.com/advisories/GHSA-fgcw-684q-jj6r), `<5.10.0` [xrqw](https://github.com/advisories/GHSA-xrqw-3rrv-vx5w), также `>=4.49.0,<=5.8.1` [x9r9](https://github.com/advisories/GHSA-x9r9-c232-4q39). Максимальная граница среди этих **изученных** advisories — `5.10.0`, не гарантия исчерпывающей безопасности. У поддерживаемой опубликованной пары Adapters 1.3.0 / Transformers >=5.10.0 **пустое пересечение**. Это технический blocker, не решение о смене SPECTER2 proximity adapter.

**Runtime evidence по линзам:** [runtime_candidates.json](../../configs/stage3/runtime_candidates.json) разделяет завершённые PubMedBERT и node2vec от пока **BLOCKED** SPECTER2. Для node2vec использован прямой Gensim backend с проверенным full-run и locked wheel проверками CI. Для SPECTER2 Adapters 1.3.0 всё ещё привязан к уязвимой ветке Transformers 4.57.x, поддерживаемая безопасная пара не найдена. Но публичный proximity checkpoint закреплён полными revision/bytes hashes: все **48 float32 tensors** на 12 BERT FFN output layers (`768→48→768`, 4 tensors/layer) прошли безопасный `torch.load(weights_only=True)` после контрольной суммы, shape/key/finite audit PASS. Детали в [public adapter evidence](../../configs/stage3/specter2_public_adapter_evidence.json).

[stage3_runtime_guard.py](../../src/pro_adherence/stage3_runtime_guard.py) продолжает отклонять несовместимые/уязвимые варианты. **Технический SPECTER2 prototype** [stage3_specter2_proximity_compat.py](../../src/pro_adherence/stage3_specter2_proximity_compat.py) не использует старую библиотеку и воспроизводит считанную из официального Adapters v1.3.0 форму выходного bottleneck layer (FFN → pre-LN → down/ReLU/up + residual → post-LN) на synthetic tensors. Независимый synthetic equation comparison `max_abs=0`; активированные настоящие веса меняют синтетический выход относительно неадаптированного BERT (`max_abs≈0.673`). **Это НЕ официальная модельная численная эквивалентность, не проверка точных base weight bytes и не inference разрешение.** Задачи до снятия blocker: подтвердить базовые веса/tokenizer точными SHA, безопасное выполнение BERT+adapter, на реальных pinned weights доказать идентичность выхода с эталонной активированной proximity реализацией, получить отдельный owner-scoped CPU scope на SPECTER2.

## 4. Строго блокирующие условия перед отдельным разрешённым compute

1. **Weights/tokenizer/adapter:** получить только выбранные полные HF revisions, установить проверенные авторитетные file SHA256 по official artifact metadata и независимо сравнить с фактически полученными bytes. Обязательные `config.json`, tokenizer files, `pytorch_model.bin` / `pytorch_adapter.bin` должны проверяться отдельно.
2. **Runtime:** node2vec использовал pin Python3.13 + пять ML wheels, зафиксированные отдельно в [hashed requirements](../../configs/stage3/node2vec_cpu_cp313_linux_x86_64.requirements.txt). Действительная CPU процедура, output identity и Git SHA зафиксированы в restricted technical acceptance. Для SPECTER2 необходим независимый безопасный exact-runtime lock и numeric adapter smoke до каких-либо вычислений. Глобальный Stage0 lock не заменяет ML runtime.
3. **Node2vec graph/model:** VERIFIED_AND_STORED: полный frozen graph 57 204 nodes/328 298 undirected edges/13 596 isolates и обученная структурная линза **43 608×128d**, исходные raw, float64 L2 norms, unit, full roster/null statuses. Source directional evidence сохранён отдельно. Model identity SHA256 `55bdf9d48fca912343f2eaf82421bd441673ac44f8714d3a460bafc1f260c5b9`; private ZIP SHA256 `51f086fb71484065f54e4a8999528417607a817019feb13eef5941f9820947b4`. Последующая семантическая оценка и Stage-gate остаются открытыми задачами.
4. **Numerical and quality checks:** node2vec 100% trained-vocabulary exact coverage, 13 596 structural null, 128d finite raw/norm/unit, нормы положительны, unit ≈1, raw≈norm×unit; полные 2×436 080 walks имеют идентичный SHA. Независимый второй implementation пересчитал исходный граф, обсервации, IDs/roster и numerical invariants; remote private Drive download+SHA+CRC PASS. SPECTER2 numerical checks pending.
5. **Owner gate:** отдельно утвердить параметры пилота, финансовый потолок и фактический запуск. Никакой локальный PASS по статическим файлам не считается таким разрешением.

## 5. Node2vec graph: restricted frozen input materialized and verified

**Граф ПОЛУЧЕН 2026-11-11** из точного frozen Stage2 research ZIP и private derived eligibility roster. Этот ZIP содержит поля citation links resolution / target_canonical_article_id / reference_ordinal, отличающиеся от GitHub one-shot schema; поэтому для настоящего frozen входа использовался **scripts/stage3_graph_frozen_streaming.py** (SQLite streaming, полная source→canonical и raw reference SHA/ordinal проверка), а не synthetic/staging helper scripts/stage3_graph_snapshot.py. Научная политика уже зафиксирована и не изменялась.

- Source input: **87 511** records, **57 293** canonical, **57 204** eligible; 2 437 863 references = **406 811** exact DOI, **223** ambiguous, **2 030 829** unresolved. Все 223 ambiguous не получают целей.
- Directed original graph: **328 383** уникальных направленных пар из 406 811 exact DOI observations, включая evidence исключённых и self-citations. Отдельный private источник сохранённых provenance: **406 811** source/ordinal/raw-export-SHA pointers.
- Eligible node2vec projection: **328 298** уникальных ненаправленных пар с weight=1, **406 729** наблюдений; 50 исключены по eligible endpoints, 32 — по self-loop (в training, **не** в original evidence). В approved eligible roster **13 596** вершин без разрешённого ребра; их vector status при обучении — missing_structural/null, не fake-zero.
- Immutable private ZIP **23 826 946 bytes**, SHA256 **33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c**. Внутри четыре deterministic gzip output плюс manifest. Manifest SHA256 **478b29cb00d837d50c3eda24d92251f2753a9fe976f02197da1f925d2fab5bd4**. Exact Drive IDs, ACL и доступ хранятся в restricted project root/рабочем учёте, не в публичном GitHub.
- Проверки **разными механизмами**: streaming input reconciliation по source references/canonical/eligibility; альтернативный полный gzip+graph-invariants scan; независимый второй прогон дал **0 byte differences**; после upload на Google Drive — отдельное скачивание и SHA256 ZIP, ZIP CRC, gzip row-count/digests; ACL owner-only/shared=false, родитель project root подтверждён.
- **Вход и итог:** immutable frozen graph ZIP SHA256 `33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c` (не ML artifact) был принят ранее; настоящий Gensim CPU node2vec 2026-11-12 **полностью обучен**, independent-check PASS и owner-only Drive readback PASS. 57 204 eligible/328 298 edges/406 729 observations; 43 608 ready 128d, 13 596 missing_structural/null. Два полных прохода 436 080 walks×40 =17 443 200 токенов в каждом, identical SHA256 `b5152add9ec72ffc036a492ab7b5d1a3d130de3d8abe91139f73b22554628ef8`. Fit 307.967 s, 4 GiB cgroup machine; peak RSS в evidence не измерялся. GitHub хранит только [production runner](../../scripts/stage3_node2vec_cpu_full_local.py), [independent auditor](../../scripts/stage3_node2vec_independent_audit.py) и synthetic tests, никаких private rows/vector IDs.

При 13 596 isolates в основном корпусе **43 608** вершин имеют наблюдаемые подтверждённые связи и обученные векторы; **13 596** остальных остаются null `missing_structural`, не нулевыми векторами. 436 080 прогулок/17 443 200 токенов на полный проход получены фактически, без хранения целого walk-list в памяти. Raw+unit для 43 608×128d ~44.65 MB uncompressed, float64 norms отдельно; полный private ZIP занимает 46 382 909 bytes. Вопрос достаточности 4 GiB для этого run решён фактом успешного завершения, но независимого измерения peak RSS нет и capacity guarantee на другую машину не заявляется.


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

**Текущие результаты Stage3 2026-11-12:** PubMedBERT 57 204/57 204 in 58 frozen ZIPs COMPLETE / VERIFIED / STORED; полный source+CLS/Mean audit и token replay 57 204, 11-article numerical re-inference PASS (technical acceptance SHA256 `4e2275151430e8f457fd57e10d80b0520684219240f64a25852eb339758fa866`). node2vec 43 608/43 608 nonisolated 128d, 13 596 isolates null, frozen direct-citation graph unchanged, entire walk-sequence replay + independent graph and numeric auditor PASS, private ZIP SHA256 `51f086fb71484065f54e4a8999528417607a817019feb13eef5941f9820947b4`, technical acceptance SHA256 `d8d65c18ba90f17c31969d98b438639034bf3c603d7d1e64260412540ac4687e`. Ни один из этих технических PASS сам по себе не доказывает внешнюю научную релевантность. SPECTER2 safe adapter runtime BLOCKED; Stage3 OPEN.

## 7. Metadata-only provenance и рассчитанный пилот (технический, не разрешённый)

[stage3_hf_provenance.py](../../src/pro_adherence/stage3_hf_provenance.py) умеет проверять inventory provider по **точному full HF revision** без загрузки весов: `--offline-snapshot` с ранее полученным JSON или явный `--online-metadata-only` (только HTTPS JSON /api/models/..., без /resolve/, pickle и inference). Проверяет revision, обязательные files и lfs SHA256 claim, но помечает все локальные byte SHA как НЕ проверенные. Metadata-only и small-file network probe фактически выполнены 2026-11-11 в двух отдельных one-shot CI и независимо readback-проверены. После этих metadata-only проверок в отдельном разрешённом P1 уже проверены и загружены локально веса PubMedBERT (§8); обычный Stage3 CI продолжает работать только на synthetic fixtures.

Команда ручной metadata-only проверки:
```bash
PYTHONPATH=src python -m pro_adherence.stage3_hf_provenance --online-metadata-only \
  --config configs/stage3/model_preflight_pins.json \
  --output /secure/hf_provider_metadata.json
```

[stage3_pilot_plan.py](../../src/pro_adherence/stage3_pilot_plan.py) — deterministic offline resource planner:
```bash
PYTHONPATH=src python -m pro_adherence.stage3_pilot_plan
```
**Node2vec local full-run resources:** total 57 204 eligible, 43 608 nonisolated, 13 596 isolates, 328 298 unique undirected edges. Полностью обучено 436 080 walks×40×1 epoch (две идентичные детерминированные итерации для build_vocab/train), CPU fit 307.967 s с `workers=1`, no paid compute. Cgroup limit 4 GiB, disk capacity sufficient; аварийная остановка памяти не сработала. Результат raw+unit float32, float64 norm и complete 57 204-status roster сохранён ZIP 46 382 909 bytes на restricted Drive; повторное скачивание и независимая реконструкция всех vector rows PASS. Peak RSS процесса специально не измерялся — не оценивать по малому пилоту.

**Фактически использованная реализация node2vec:** original frozen binary undirected graph, first-order uniform p=q=1, Gensim 4.4.0 skip-gram `sg=1`, `hs=0`, `negative=5`, `sample=0.001`, `dim=128`, `walk_length=40`, `walks_per_node=10`, `window=10`, `epochs=1`, `seed=20261031`, `min_count=1`, `workers=1`, stable SHA-derived word hash, sorted vocabulary. Весь run воспроизводим по [публичному коду](../../scripts/stage3_node2vec_cpu_full_local.py), точному SHA graph, model identity, 5-wheel hash pins и restricted immutable input/output. Exact clean reinstall on ephemeral compute machine и full independent *model retraining* не проводились; независимая проверка графа/vector bytes и two-pass walk hash сделана.

**Фактический compute verification:** перед полным расчётом restricted graph SHA/ZIP CRC/member hashes PASS, версии Python 3.13.5/Gensim 4.4.0/Numpy 2.3.5/SciPy 1.17.0/smart-open 7.6.1/wrapt 2.2.1 совпали с pin; после расчёта ready=43 608, isolate=13 596, full walk passes 2×436 080/17 443 200, identical SHA, 128d float32 finite vectors, unit norm reconstruction PASS. Independent code [stage3_node2vec_independent_audit.py](../../scripts/stage3_node2vec_independent_audit.py) повторно сверил source→canonical, 328 298 edges, 406 729 eligible observations и все 57 204 output status rows. Private archive SHA и ACL owner-only удалённо подтверждены.

**Дальнейшая научно-техническая граница:** node2vec production compute и owner-only QA завершены; не запускать повторный full training без отдельного решения. Результаты готовятся к будущим кластерам/neighbor analyses только по следующему владельческому scope. Для смысловой валидности необходимы отдельная оценка relevancy и корректные независимые научные controls; совпадение с citation graph не является внешним подтверждением node2vec. SPECTER2 остаётся BLOCKED без безопасного adapter runtime. Stage3 Stage-gate не закрывается автоматически.

Полный план — REPRESENTATION_IMPLEMENTATION_PLAN §5.

**Owner gate:** полный бесплатный node2vec CPU run отдельно разрешён владельцем 2026-11-12 и выполнен. Это разрешение исчерпано; ни новый полный прогон, ни платные ресурсы, ни SPECTER2 inference, ни public release, ни PR merge, ни Stage transition автоматически не разрешены.

**Сохранённые завершённые линзы:** PubMedBERT 57 204/57 204, 58 private ZIPs, full independent source/numeric/token replay PASS; node2vec 43 608/43 608 nonisolated structural vectors, 13 596 null isolates, full independent graph/vector audit PASS. Межлинзовая согласованность и цитатная структура не должны выдаваться за независимую проверку node2vec. Stage3 OPEN до решения владельца.

## 8. Актуальный model provenance и исполненные PubMedBERT P1 + полный run (2026-11-12)

Поставщик HF подтвердил неизменные model commits и LFS SHA; все девять обязательных малых configuration/tokenizer files ранее побайтово проверены. Единственный **фактически скачанный и сверенный по локальным bytes весовой файл** теперь — PubMedBERT `pytorch_model.bin`, SHA256 `d513412d396cecec5f67936ac871b4aaf1178dfb5193776e790fd2b28bba240c` (440 474 434 bytes). Его frozen encoder (CLS и mean, 768d) выполнил разрешённый бесплатный P1 на **1 000** статьях за **183,4 с**, 1 075 проходов без потери текста. Использованы torch 2.10.0+cpu и transformers 5.22.2; weights и config byte-readback PASS. Подробности и закрытый output ZIP SHA256 `5cb706e8b1fe9f210cd99cc4c2a10764447d500c9b742290917b314e75108844` — [FIRST_PILOT.md](./FIRST_PILOT.md).

**Статус scientific representation:** PubMedBERT и node2vec полностью рассчитаны, в restricted Drive и независимо QA-верифицированы. SPECTER2 proximity **PUBLIC ADAPTER BYTES VERIFIED / EXPERIMENTAL ALGEBRA PROBE PASS / FULL RUNTIME BLOCKED**: exact 12-layer/48-tensor checkpoint и adapter config SHA проверены, но base bytes, безопасная поддерживаемая связка, official adapter-activated numeric equivalence и SPECTER2 inference отсутствуют. Внешняя научная relevance validation также не выполнена. Stage3 OPEN; heavy compute/release/Stage-gate остаются отдельными решениями владельца.
