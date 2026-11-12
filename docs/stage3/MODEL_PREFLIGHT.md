# Stage 3 — закрытый census и preflight трёх линз (SCOPED EXECUTION)

**Единственный текущий статус проекта:** [07_STAGE_STATUS](https://docs.google.com/document/d/1GhQfnsbxK8lilvpnZqWeFu99w67DwWKJmY5OTthxvhM/edit), Stage 3 **OPEN / EXECUTION — SCOPED PUBMEDBERT CPU**, owner decision 2026-11-12. Последовательные owner-scoped 4k CPU пакеты 019–022, 023–026 и 027–030 выполнены и независимо подтверждены на restricted Google Drive. Актуальное полное покрытие **31 000 / 57 204** (54,2 %), следующий невычисленный шард 031. После этого поручения дальнейший 031+ compute требует нового scope. SPECTER2 inference, node2vec training, оплачиваемые сервисы, публичный релиз/PR merge и переход Stage не разрешены. Данный документ — технический preflight, не выдаёт новых разрешений.

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

**Исходные кандидаты package metadata (не полный exact lock):** [runtime_candidates.json](../../configs/stage3/runtime_candidates.json). Для PubMedBERT кандидатом закреплён `transformers==5.22.2` с [официальным PyPI wheel SHA256](https://pypi.org/project/transformers/5.22.2/) `829c2820aff91730b8ec45a4b8ff4be07f586a140b68a9073998b36fa35297dc`; Python, torch, tokenizers и compatibility smoke ещё отсутствуют. Для node2vec только `node2vec==0.5.0`, не закреплены остальные dependency hashes. Для SPECTER2 последний published `adapters==1.3.0`: wheel SHA256 `c0620b1b98df4af3876aa1e053ba43d0a19d82e62fc6a3ebc67d158183e07919` ([PyPI](https://pypi.org/project/adapters/1.3.0/)), **но безопасного подтверждённого Transformers runtime нет**. SHA на странице провайдера ≠ checksum скачанного wheel.

[stage3_runtime_guard.py](../../src/pro_adherence/stage3_runtime_guard.py) проверяет конкретные known advisories и несовместимость; [stage3_preflight.py](../../src/pro_adherence/stage3_preflight.py) не принимает формальный hash вместо проверенных bytes. Для безопасного runtime SPECTER2 нужны новые официальные dependency metadata/поддерживаемая безопасная реализация, отдельный lock с hash wheel и настоящий adapter-activated numeric smoke, затем comparison на неизменном научном конфиге. **Нельзя считать установленной заведомо уязвимую пару ради smoke.** Для PubMedBERT реальный CPU runtime проверен разрешённым P1; SPECTER2 всё ещё **BLOCKED**, node2vec training runtime **PENDING**.

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
- Граф — **derived non-model artifact**, не trained node2vec model и не grant compute. Runtime, HF model file SHA/weights, trained-model identity и owner compute permission остаются PENDING. Node2vec training **НЕ** запускался.

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

**Статус 2026-11-12:** restricted cohort and node2vec graph VERIFIED_AND_STORED, HF revisions PINNED. PubMedBERT frozen model+tokenizer bytes SHA verified, torch 2.10.0+cpu and transformers 5.22.2 used with CPU threads=2 for shard pair 027–030; full 31k PubMedBERT input SHA `1611f07e18ccf999493938e552d1a73ad049db931a11399fc01f0ca7b07dc053`. Four latest immutable ZIPs and private full audit passed remote byte SHA, ZIP CRC and owner-only ACL readback. Independent complete 31 ZIP/31 000 ID source + numerical invariant audit PASS, report SHA256 `45d9588f2a41e492b01a8e5deabae60a574d77104365388e5bc4ebe7d17815d5`, saved auditor SHA256 `f877a0a3f2b5d759f1f1cb8953266f5a7e5a6c49423aa4c199f39e4006769016`. Legacy static three-lens preflight config `PLANNING_ONLY_NO_INFERENCE` is a fail-closed synthetic guard, NOT live Stage status (07_STAGE_STATUS rules). SPECTER2 safe adapter runtime remains BLOCKED; node2vec training PENDING. Next shard 031 awaits next owner scope; other model compute, release and Stage transition NOT authorized.

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

**Действующий verified PubMedBERT CPU progress 2026-11-12:** **31 000 / 57 204** eligible canonical IDs, immutable private ZIP shards 000–030 saved/read back, last owner-requested package 027–030 complete with 4 290 fragment passes, 283 fragmented articles, 531 title-only, zero forced splits/fallback, $0 external cost. 31/31 ZIP file SHA, content hashes/CRC, source record IDs/text state and CLS+Mean raw/norm/unit invariants PASS; latest 31k audit and exact auditor source saved restricted on Drive. Next unopened boundary 031. Upstream scientific method unchanged; no private embeddings/public corpus disclosed. Details: [REPRESENTATION_IMPLEMENTATION_PLAN.md](./REPRESENTATION_IMPLEMENTATION_PLAN.md) and 07_STAGE_STATUS.

## 8. Актуальный model provenance и состоявшийся PubMedBERT P1 (2026-11-11)

Поставщик HF подтвердил неизменные model commits и LFS SHA; все девять обязательных малых configuration/tokenizer files ранее побайтово проверены. Единственный **фактически скачанный и сверенный по локальным bytes весовой файл** теперь — PubMedBERT `pytorch_model.bin`, SHA256 `d513412d396cecec5f67936ac871b4aaf1178dfb5193776e790fd2b28bba240c` (440 474 434 bytes). Его frozen encoder (CLS и mean, 768d) выполнил разрешённый бесплатный P1 на **1 000** статьях за **183,4 с**, 1 075 проходов без потери текста. Использованы torch 2.10.0+cpu и transformers 5.22.2; weights и config byte-readback PASS. Подробности и закрытый output ZIP SHA256 `5cb706e8b1fe9f210cd99cc4c2a10764447d500c9b742290917b314e75108844` — [FIRST_PILOT.md](./FIRST_PILOT.md).

**Не путать завершение P1 с full run:** exact весь Python dependency lock для будущего масштабного compute всё ещё не утверждён, SPECTER2 base+proximity model weights не скачаны и безопасный runtime не найден, trained node2vec нет. Для них предварительно доступны только authoritative LFS hashes: SPECTER2 base `801eda968fad1752fe846a8e572bfdc25202be85544680dda4c99f4589646ebc`, proximity `5b6105714f78b294daa7e2d181134df12f0acb7a4ec7c1e3c13e512c908db94a`. Научные параметры не менялись; Stage gate и permission на полный или платный run отсутствуют.
