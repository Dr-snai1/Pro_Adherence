# Stage 3 — закрытый census и preflight трёх линз (SCOPED EXECUTION)

**Единственный текущий статус проекта:** [07_STAGE_STATUS](https://docs.google.com/document/d/1GhQfnsbxK8lilvpnZqWeFu99w67DwWKJmY5OTthxvhM/edit): Stage 3 **OPEN / EXECUTION — SCOPED PUBMEDBERT CPU**, NOT CLOSED. **PubMedBERT execution lane COMPLETE / VERIFIED / STORED, 57 204 / 57 204 (100%)**; complete fresh 58-ZIP source/CLS+Mean numerical audit, full 57 204-article frozen tokenizer replay and 11-record model re-inference PASS. Final independent technical acceptance SHA256 `4e2275151430e8f457fd57e10d80b0520684219240f64a25852eb339758fa866` saved in restricted Drive with actual readback. Next read-only node2vec graph check PASS but its training and SPECTER2 inference, paid compute, public data release, PR merge and Stage4 remain UNAUTHORIZED; no implicit Stage closure or scientific methodology change.

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

Список обязательных файлов и ссылки на verified public commit pages: `configs/stage3/model_preflight_pins.json`. Указанные full commit SHAs **не равны** SHA256 скачанных бинарных весов. Provider LFS SHA256 трёх весовых файлов подтверждены по pinned HF revision metadata; девять config/tokenizer файлов проверены byte SHA256 и provider Git blob. **PubMedBERT веса теперь получены и проверены**, SPECTER2 весовые файлы остаются непроверенными; §8. Нельзя объявлять `model_identity_hash` готовым по одному только адресу репозитория или короткому SHA.

## 3. ML runtime: безопасные раздельные кандидаты, SPECTER2 BLOCKED

На 2026-11-11 последний опубликованный [Adapters 1.3.0](https://pypi.org/project/adapters/1.3.0/) требует `transformers~=4.57.6` (то есть >=4.57.6,<4.58.0) по [исходному setup.py](https://github.com/adapter-hub/adapters/blob/v1.3.0/setup.py). Официальные GHSA: версии `<5.3.0` [29pf](https://github.com/advisories/GHSA-29pf-2h5f-8g72), `<5.5.0` [fgcw](https://github.com/advisories/GHSA-fgcw-684q-jj6r), `<5.10.0` [xrqw](https://github.com/advisories/GHSA-xrqw-3rrv-vx5w), также `>=4.49.0,<=5.8.1` [x9r9](https://github.com/advisories/GHSA-x9r9-c232-4q39). Максимальная граница среди этих **изученных** advisories — `5.10.0`, не гарантия исчерпывающей безопасности. У поддерживаемой опубликованной пары Adapters 1.3.0 / Transformers >=5.10.0 **пустое пересечение**. Это технический blocker, не решение о смене SPECTER2 proximity adapter.

**Исходные кандидаты package metadata (не полный exact lock):** [runtime_candidates.json](../../configs/stage3/runtime_candidates.json). Первоначальный кандидат PubMedBERT `transformers==5.22.2` с [официальным PyPI wheel SHA256](https://pypi.org/project/transformers/5.22.2/) `829c2820aff91730b8ec45a4b8ff4be07f586a140b68a9073998b36fa35297dc` фактически использован с `torch 2.10.0+cpu`; локальный byte-pinned model/encoder smoke, 58-shard inference и независимый numerical/sample replay PASS. Этот runtime факт не является полным lock для остальных ещё не запущенных ML линз. Для node2vec только `node2vec==0.5.0`, не закреплены остальные dependency hashes. Для SPECTER2 последний published `adapters==1.3.0`: wheel SHA256 `c0620b1b98df4af3876aa1e053ba43d0a19d82e62fc6a3ebc67d158183e07919` ([PyPI](https://pypi.org/project/adapters/1.3.0/)), **но безопасного подтверждённого Transformers runtime нет**. SHA на странице провайдера ≠ checksum скачанного wheel.

[stage3_runtime_guard.py](../../src/pro_adherence/stage3_runtime_guard.py) проверяет конкретные known advisories и несовместимость; [stage3_preflight.py](../../src/pro_adherence/stage3_preflight.py) не принимает формальный hash вместо проверенных bytes. Для безопасного runtime SPECTER2 нужны новые официальные dependency metadata/поддерживаемая безопасная реализация, отдельный lock с hash wheel и настоящий adapter-activated numeric smoke, затем comparison на неизменном научном конфиге. **Нельзя считать установленной заведомо уязвимую пару ради smoke.** Для PubMedBERT реальный CPU runtime проверен P1, полным 57 204 batch и новым независимым sample replay; SPECTER2 всё ещё **BLOCKED**, node2vec training runtime **PENDING**.

## 4. Строго блокирующие условия перед отдельным разрешённым compute

1. **Weights/tokenizer/adapter:** получить только выбранные полные HF revisions, установить проверенные авторитетные file SHA256 по official artifact metadata и независимо сравнить с фактически полученными bytes. Обязательные `config.json`, tokenizer files, `pytorch_model.bin` / `pytorch_adapter.bin` должны проверяться отдельно.
2. **Runtime:** зафиксировать *отдельный* совместимый dependency lock для модельных вычислений (PyTorch, transformers, tokenizers и adapters для SPECTER2; node2vec backend), версии Python/GPU/CPU и hashes. Действующий Stage0 lock **не содержит** этих ML-библиотек и не считается готовым ML runtime. Совместимость SPECTER2 adapter проверяется в целевом runtime техническим smoke test — не открывать научную развилку.
3. **Node2vec graph:** VERIFIED_AND_STORED: sorted 57 204 eligible node map + immutable directed citation observations + binary undirected training projection and isolates, private Drive SHA and independent readback (§5). Trained model identity/runtime и owner compute gate остаются PENDING.
4. **Numerical and quality checks:** только после отдельного решения о вычислениях валидировать размерности 768/128, pooled/text policies, raw/norm/unit, cosine, null statuses, SPECTER2 token loss; у node2vec проверить reproducible walks/seed без навязанного поиска новых гиперпараметров.
5. **Owner gate:** отдельно утвердить параметры пилота, финансовый потолок и фактический запуск. Никакой локальный PASS по статическим файлам не считается таким разрешением.

## 5. Node2vec graph: restricted frozen input materialized and verified

**Граф ПОЛУЧЕН 2026-11-11** из точного frozen Stage2 research ZIP и private derived eligibility roster. Этот ZIP содержит поля citation links resolution / target_canonical_article_id / reference_ordinal, отличающиеся от GitHub one-shot schema; поэтому для настоящего frozen входа использовался **scripts/stage3_graph_frozen_streaming.py** (SQLite streaming, полная source→canonical и raw reference SHA/ordinal проверка), а не synthetic/staging helper scripts/stage3_graph_snapshot.py. Научная политика уже зафиксирована и не изменялась.

- Source input: **87 511** records, **57 293** canonical, **57 204** eligible; 2 437 863 references = **406 811** exact DOI, **223** ambiguous, **2 030 829** unresolved. Все 223 ambiguous не получают целей.
- Directed original graph: **328 383** уникальных направленных пар из 406 811 exact DOI observations, включая evidence исключённых и self-citations. Отдельный private источник сохранённых provenance: **406 811** source/ordinal/raw-export-SHA pointers.
- Eligible node2vec projection: **328 298** уникальных ненаправленных пар с weight=1, **406 729** наблюдений; 50 исключены по eligible endpoints, 32 — по self-loop (в training, **не** в original evidence). В approved eligible roster **13 596** вершин без разрешённого ребра; их vector status при обучении — missing_structural/null, не fake-zero.
- Immutable private ZIP **23 826 946 bytes**, SHA256 **33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c**. Внутри четыре deterministic gzip output плюс manifest. Manifest SHA256 **478b29cb00d837d50c3eda24d92251f2753a9fe976f02197da1f925d2fab5bd4**. Exact Drive IDs, ACL и доступ хранятся в restricted project root/рабочем учёте, не в публичном GitHub.
- Проверки **разными механизмами**: streaming input reconciliation по source references/canonical/eligibility; альтернативный полный gzip+graph-invariants scan; независимый второй прогон дал **0 byte differences**; после upload на Google Drive — отдельное скачивание и SHA256 ZIP, ZIP CRC, gzip row-count/digests; ACL owner-only/shared=false, родитель project root подтверждён.
- Граф — **derived non-model artifact**, не trained node2vec model и не grant compute. После PubMedBERT final acceptance независимый **read-only graph rescan** снова подтвердил SHA256 графа `33fe8b481e0b1040ff2fbe1c0a9bb376811aed3ab2157389de03554bc95da67c`, ZIP CRC/internal hashes, 57 204 eligible nodes, 328 298 уникальных binary unordered training edges (без self loops/duplicates), 13 596 isolates и 406 729 observed eligible links; report SHA256 `d1fbe3628a90cee9da92da91f2810304ca7201013daff8e206d7f0ac9f068e71` preserved restricted. Runtime exact lock, trained-model identity и owner compute authorization PENDING. **No walks or training** performed.

При 13 596 isolates только **43 608** nonisolated training nodes дают **436 080** walks / **17 443 200** nominal 40-step tokens (без фиктивных прогулок изолятов). Нижняя упаковка integer tokens — 69 772 800 bytes; Python peak RAM не измерен. Степени из restricted graph: p50=9, p90=33, p99=95, max=2 714; raw+unit float32 128d для nonisolated = 44 654 592 bytes. Полный ресурсный план — §7.


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

**Статус 2026-11-12:** PubMedBERT 58 immutable private ZIPs `000`–`057`, **57 204 / 57 204 (100%)**, approved frozen source/model/method unchanged. Rerun independent full ZIP/source/CLS+Mean raw/norm/unit numeric audit PASS; byte-identical previous report SHA256 `da46a8bc57c385a1feb8dbc5a67c88862f379163a328b7c346176f9d5248d687`. **New complete tokenizer replay across ALL 57 204 articles** PASS: 61 547 fragments, one necessary nonlossy forced split, 0 fallbacks, 0 lost/duplicated/truncated tokens, SHA256 `0e63a0c6579017c789df40eff4edfb2aa5ee203d6f20808d0b88fd79e6a22518`. Independently rerun pinned PubMedBERT on 11 fixed records (including forced split and final partial shard), raw CLS max_abs 1.1445e-5, Mean 1.9074e-6 under 5e-5 numeric tolerance, PASS; report SHA256 `bfbddd8f8f4da52ddd53845a76d0c454ac014b01a534a2cde8fb643ea7ed2f62`. 26 repeated-vector groups/28 extra rows reflect identical raw text or tokenizer-equivalent strings, 0 unexplained pairs. Final private acceptance SHA256 `4e2275151430e8f457fd57e10d80b0520684219240f64a25852eb339758fa866`, all new evidence and scripts byte-verified from owner-only Drive. Node2vec graph read-only verification PASS, trained embedding PENDING; SPECTER2 adapter safe runtime BLOCKED, no paid compute or Stage change.

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
Фактические агрегаты: 57 204 eligible, 43 608 nonisolated, 17 443 200 node2vec walk tokens; условная float32 raw+unit storage при полном покрытии текстом и без других служебных структур — **1 099 038 720 bytes (~1 048 MiB)**. Это **не** RAM peak, не размер моделей и не измеренный GPU-hour budget. Время/cost остаются `null`, пока нет measured articles/sec / walk tokens/sec и подтверждённой цены ресурса; walk speed отдельно не включает Word2Vec training. Пилотный технический smoke на 64 стратифицированных входах является частью возможного P1 до ~1 000, но он не запущен и **не санкционирован**. Полный план — REPRESENTATION_IMPLEMENTATION_PLAN `5.

**Owner gate:** после локального verified model byte readback, package wheel hash lock, SPECTER2 numeric compatibility smoke и измеренного resource pilot представить bounded compute proposal, расходы и критерии STOP. Никакого тяжёлого run/оплаты/Stage transition сейчас.

**Действующий verified PubMedBERT CPU progress 2026-11-12:** **57 204 / 57 204 (100%), COMPLETE / VERIFIED / STORED**. Exactly 58 accepted restricted ZIPs, final shard 057=204 records; 57 204 unique canonical IDs and both separate 768d CLS/Mean raw, float64 norms and unit vectors. Full archived source/numerical audit and ALL-source tokenizer replay PASS; 11-article independent encoder spot re-inference PASS. Technical signoff SHA256 `4e2275151430e8f457fd57e10d80b0520684219240f64a25852eb339758fa866` stored restricted. No remaining PubMedBERT inference. This technical QA is not external semantic relevance validation and does not authorize Stage3 gate closure or node2vec/SPECTER2 compute. Exact evidence IDs in authoritative 07_STAGE_STATUS and approved method in [REPRESENTATION_IMPLEMENTATION_PLAN.md](./REPRESENTATION_IMPLEMENTATION_PLAN.md).

## 8. Актуальный model provenance и исполненные PubMedBERT P1 + полный run (2026-11-12)

Поставщик HF подтвердил неизменные model commits и LFS SHA; все девять обязательных малых configuration/tokenizer files ранее побайтово проверены. Единственный **фактически скачанный и сверенный по локальным bytes весовой файл** теперь — PubMedBERT `pytorch_model.bin`, SHA256 `d513412d396cecec5f67936ac871b4aaf1178dfb5193776e790fd2b28bba240c` (440 474 434 bytes). Его frozen encoder (CLS и mean, 768d) выполнил разрешённый бесплатный P1 на **1 000** статьях за **183,4 с**, 1 075 проходов без потери текста. Использованы torch 2.10.0+cpu и transformers 5.22.2; weights и config byte-readback PASS. Подробности и закрытый output ZIP SHA256 `5cb706e8b1fe9f210cd99cc4c2a10764447d500c9b742290917b314e75108844` — [FIRST_PILOT.md](./FIRST_PILOT.md).

**PubMedBERT P1 и полный run подтверждены отдельно:** обе разрешённые вычислительные части завершены, полное покрытие 57 204/57 204 подтверждено новым техническим audit. Для будущих SPECTER2 base+proximity остаются неподтверждёнными downloaded weight bytes, supported safe adapter runtime и exact dependency lock; trained node2vec тоже отсутствует, training lock и compute gate pending. Публичные provider LFS SHA256 для SPECTER2 base `801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc`, proximity `5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a` пока не заменяют actual weight byte verification. Stage3 OPEN, scientific settings frozen, unrelated heavy compute and paid resources not authorized.
