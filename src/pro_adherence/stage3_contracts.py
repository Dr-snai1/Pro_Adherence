"""Stage 3 planning-only, synthetic-testable contracts (NO model or graph training).

This module never downloads scientific records, loads transformer weights, trains
node2vec, or publishes private data. All scientific choices are supplied explicitly.
The frozen 57,293-group Stage 2 release remains authoritative on private Drive.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import math
import re


class Stage3ContractError(ValueError):
    """Refuse an implicit scientific parameter, invented link or lost provenance."""


SHA256 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_REFERENCE_STATUS = {"exact_doi", "ambiguous_doi", "unresolved"}
FROZEN_STAGE2_ZIP_SHA256 = (
    "a76f8cd2acae907c163c417e1ccc7900275f6c12a1e689d591c922b865d41127"
)


def _unique_index(rows: list[dict], key: str, label: str) -> dict:
    result = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise Stage3ContractError(f"{label}: missing {key}")
        if value in result:
            raise Stage3ContractError(f"{label}: duplicate {key}={value}")
        result[value] = row
    return result


def _exact_coverage(label: str, mapping: dict, ids: set[str]) -> None:
    if set(mapping) != ids:
        raise Stage3ContractError(
            f"{label}: missing={len(ids - set(mapping))} extra={len(set(mapping) - ids)}"
        )


def freeze_snapshot_contract(snapshot: dict) -> dict:
    """Preflight the *accepted* private Stage2 identity; no input bytes are read."""
    expected = {
        "archive_sha256": FROZEN_STAGE2_ZIP_SHA256,
        "source_record_count": 87511,
        "canonical_article_count": 57293,
    }
    for key, val in expected.items():
        if snapshot.get(key) != val:
            raise Stage3ContractError(f"Stage2 snapshot mismatch: {key}")
    if snapshot.get("access_class") != "restricted":
        raise Stage3ContractError("Stage2 is restricted, not a public corpus")
    return dict(expected, access_class="restricted")


def validate_model_readiness(lens: str, specification: dict) -> None:
    """Fail closed until owner scientific choices and immutable weights are pinned.

    A technically valid specification is not an authorization to run inference.
    The calling code must separately check the Stage gate / owner permission.
    """
    if lens not in {"pubmedbert", "specter2", "node2vec"}:
        raise Stage3ContractError("unknown Stage3 lens")
    if specification.get("scientific_parameters_status") != "owner_approved":
        raise Stage3ContractError("scientific parameters not owner-approved")
    if not SHA256.fullmatch(str(specification.get("config_sha256", ""))):
        raise Stage3ContractError("missing immutable scientific config SHA")
    if lens == "pubmedbert":
        # Owner decision (2026-11-09): MetSyn reproducibility is NOT a scientific
        # requirement for Pro_Adherence. Pooling/segmentation and other choices
        # are methodological variables; they must be recorded and approved
        # independently, not inherited as unexamined defaults from MetSyn.
        for name in (
            "methodology_decision_ref", "model_ref_id", "model_identity_hash",
            "tokenizer_identity", "title_abstract_format", "pooling",
            "normalization", "max_length", "overflow_policy",
        ):
            if specification.get(name) is None or specification.get(name) == "":
                raise Stage3ContractError(f"unresolved PubMedBERT methodology: {name}")
        if not SHA256.fullmatch(str(specification["model_identity_hash"])):
            raise Stage3ContractError("unverified PubMedBERT model identity")
        # Owner's 2026-11-09 decisions; do not broaden the scientific scope.
        chosen = {
            "pretraining_corpus": "pubmed_abstracts",
            "embedding_dimension": 768,
            "layer_selection": "last_hidden",
            "title_abstract_format": "title_sep_abstract",
            "max_length": 512,
            "overflow_policy": "fragmented",
            "fine_tuning": False,
        }
        for name, approved_value in chosen.items():
            if name not in specification or specification[name] != approved_value:
                raise Stage3ContractError(f"PubMedBERT owner decision mismatch: {name}")
        if specification["pooling"] not in ("cls_last_hidden", "masked_mean_last_hidden"):
            raise Stage3ContractError("PubMedBERT pooling must be CLS or masked mean")
        if specification["normalization"] != "l2_after_article_aggregation":
            raise Stage3ContractError("PubMedBERT owner decision: L2 only after full article aggregation")
        if specification.get("similarity_metric") != "cosine":
            raise Stage3ContractError("PubMedBERT owner decision: cosine similarity required")
        if specification.get("raw_vector_retention") is not True:
            raise Stage3ContractError("PubMedBERT raw vector and norm must be retained")
        # Both choices are authorised as distinct variants, NOT an arbitrary
        # concatenation or a forced choice between them.
        # Multi-fragment article aggregation is a further scientific variable,
        # not specified by choosing a 512-token fragment size.
        if specification.get("fragment_aggregation") != "content_token_weighted_mean":
            raise Stage3ContractError("PubMedBERT owner decision: token-weighted fragment aggregation required")
        if specification.get("special_tokens_policy") != "exclude_all_special_and_padding":
            raise Stage3ContractError("PubMedBERT mean must exclude all special tokens and padding")
    elif lens == "specter2":
        # Owner-approved scientific config (2026-11-10); immutable model
        # revisions and actual artifact SHA256 values still require preflight.
        for name in (
            "base_model_ref", "base_model_revision", "base_model_identity_hash",
            "adapter_ref", "adapter_revision", "adapter_identity_hash",
            "model_identity_hash", "tokenizer_identity", "tokenizer_revision",
            "input_format", "max_length", "embedding_dimension",
            "output_pooling", "adapter_task", "overflow_policy",
            "text_source_policy", "title_only_policy",
            "normalization", "similarity_metric", "raw_vector_retention",
            "token_loss_report", "fine_tuning",
        ):
            if specification.get(name) is None or specification.get(name) == "":
                raise Stage3ContractError(f"unresolved SPECTER2 {name}")
        for name in ("base_model_identity_hash", "adapter_identity_hash", "model_identity_hash"):
            if not SHA256.fullmatch(str(specification[name])):
                raise Stage3ContractError(f"invalid SPECTER2 {name}")
        for name in ("base_model_revision", "adapter_revision", "tokenizer_revision"):
            if not re.fullmatch(r"[0-9a-f]{40}", str(specification[name])):
                raise Stage3ContractError(f"SPECTER2 immutable HF revision required: {name}")
        approved = {
            "base_model_ref": "allenai/specter2_base",
            "adapter_ref": "allenai/specter2",
            "adapter_task": "proximity",
            "input_format": "title_sep_abstract",
            "max_length": 512,
            "embedding_dimension": 768,
            "output_pooling": "last_hidden_first_token",
            "overflow_policy": "truncate_512_report_token_loss",
            "text_source_policy": "pubmed_wos_apa_complete_first",
            "title_only_policy": "only_if_no_abstract_in_any_source",
            "normalization": "l2_after_final_article_vector",
            "similarity_metric": "cosine",
            "raw_vector_retention": True,
            "token_loss_report": True,
            "fine_tuning": False,
        }
        for name, expected in approved.items():
            if specification[name] != expected or type(specification[name]) is not type(expected):
                raise Stage3ContractError(f"SPECTER2 owner decision mismatch: {name}")
    else:
        for name in ("graph_snapshot_sha256", "model_ref_id", "model_identity_hash",
                     "walk_length", "walks_per_node", "window", "epochs",
                     "dimension", "p", "q", "seed", "isolate_policy",
                     "graph_orientation", "source_graph_orientation",
                     "edge_weight_policy", "self_loop_policy",
                     "normalization", "similarity_metric", "raw_vector_retention"):
            if specification.get(name) is None:
                raise Stage3ContractError(f"unresolved node2vec {name}")
        if not SHA256.fullmatch(str(specification["graph_snapshot_sha256"])):
            raise Stage3ContractError("node2vec graph not pinned")
        if not SHA256.fullmatch(str(specification["model_identity_hash"])):
            raise Stage3ContractError("node2vec model identity not pinned")
        # Owner-approved node2vec baseline (2026-11-10):
        # p=q=1 and embedding dimension=128. Other graph/walk choices remain open.
        if (type(specification["p"]) not in (float, int)
            or type(specification["q"]) not in (float, int)
            or not math.isfinite(specification["p"])
            or not math.isfinite(specification["q"])
            or specification["p"] != 1 or specification["q"] != 1):
            raise Stage3ContractError("node2vec owner decision requires p=1 and q=1")
        if type(specification["dimension"]) is not int or specification["dimension"] != 128:
            raise Stage3ContractError("node2vec owner decision requires dimension=128")
        approved = {
            "walk_length": 40,
            "walks_per_node": 10,
            "window": 10,
            "epochs": 1,
            "seed": 20261031,
            "isolate_policy": "missing_structural",
            "graph_orientation": "undirected",
            "source_graph_orientation": "directed",
            "edge_weight_policy": "binary_unique_unordered_pair",
            "self_loop_policy": "exclude",
            "normalization": "l2_after_training",
            "similarity_metric": "cosine",
            "raw_vector_retention": True,
        }
        for name, expected in approved.items():
            value = specification[name]
            if (value != expected or type(value) is not type(expected)):
                raise Stage3ContractError(
                    f"node2vec owner decision mismatch: {name}")




PUBMEDBERT_SOURCE_PRIORITY = ("pubmed", "woscc", "apa_psycinfo")


def choose_pubmedbert_source_priority(
    canonical_articles: list[dict], source_records: list[dict]
) -> dict[str, str]:
    """Owner-selected fixed source priority: PubMed > WoS > APA.

    Prefer a complete title+abstract from ONE source record, then a title-only
    record if no complete record exists. plan_text_inputs flags title-only as
    pending when any other member has an abstract; NEVER combine source fields
    silently. Source ID is a deterministic tie-breaker within one database.
    """
    articles = _unique_index(canonical_articles, "canonical_article_id", "canonical")
    sources = _unique_index(source_records, "source_record_id", "source")
    choices = {}
    for article_id, article in sorted(articles.items()):
        member_ids = article.get("source_record_ids")
        if not isinstance(member_ids, list) or not member_ids:
            raise Stage3ContractError("canonical article has no source members")
        if len(member_ids) != len(set(member_ids)):
            raise Stage3ContractError("duplicate canonical source members")
        candidates = []
        for member_id in member_ids:
            member = sources.get(member_id)
            if member is None:
                raise Stage3ContractError(f"missing source record {member_id}")
            db = member_id.split(":", 1)[0]
            if db not in PUBMEDBERT_SOURCE_PRIORITY:
                raise Stage3ContractError(f"unsupported PubMedBERT source prefix {db}")
            title, abstract = member.get("title") or "", member.get("abstract") or ""
            if not isinstance(title, str) or not isinstance(abstract, str):
                raise Stage3ContractError("invalid PubMedBERT source text")
            complete = bool(title.strip() and abstract.strip())
            has_title = bool(title.strip())
            # Completeness protects earlier title-only decision: lower-priority
            # complete text is preferable to discarding an available abstract.
            candidates.append((
                0 if complete else 1 if has_title else 2,
                PUBMEDBERT_SOURCE_PRIORITY.index(db),
                member_id,
            ))
        choices[article_id] = min(candidates)[2]
    return choices


def normalize_stage3_source_flags(raw_source_records: list[dict]) -> list[dict]:
    """Preserve actual Stage2 flag-exposure semantics; never turn absent into False.

    Stage2 exposes APA's retracted_article / peer_review_unknown and WoS's
    cited_references_count_anomaly. Their absence on other source families is
    *not_exposed*, not a negative scientific finding. True flags from any
    additional explicitly exposed source are still preserved.
    """
    supported_source_fields = {
        "pubmed": (),
        "woscc": ("cited_references_count_anomaly",),
        "apa_psycinfo": ("retracted_article", "peer_review_unknown"),
    }
    logical_to_original = {
        "is_retracted": "retracted_article",
        "peer_review_unknown": "peer_review_unknown",
        "wos_nr_cr_mismatch": "cited_references_count_anomaly",
    }
    normalized = []
    for raw in raw_source_records:
        source_id = raw.get("source_id")
        record_id = raw.get("source_record_id")
        if source_id not in supported_source_fields:
            raise Stage3ContractError("unrecognized Stage2 source family")
        if not isinstance(record_id, str) or not record_id.startswith(source_id + ":"):
            raise Stage3ContractError("source ID/prefix mismatch")
        family = raw.get("record_family")
        if family not in {"journal", "book", "unknown"}:
            raise Stage3ContractError("invalid raw record_family")
        export_sha = raw.get("raw_export_sha256")
        ordinal = raw.get("raw_record_ordinal")
        if not SHA256.fullmatch(str(export_sha)):
            raise Stage3ContractError("Stage2 raw export identity required")
        if type(ordinal) is not int or ordinal < 1:
            raise Stage3ContractError("Stage2 raw record ordinal required")
        flags = {}
        for logical, original in logical_to_original.items():
            if original in supported_source_fields[source_id] and original not in raw:
                raise Stage3ContractError(
                    f"missing declared Stage2 {source_id} flag: {original}")
            value = raw.get(original) if original in raw else None
            if value is not None and type(value) is not bool:
                raise Stage3ContractError(f"invalid Stage2 flag value: {original}")
            flags[logical] = value
        normalized.append({
            "source_record_id": record_id,
            "source_id": source_id,
            "record_family": family,
            "raw_export_sha256": export_sha,
            "raw_record_ordinal": ordinal,
            **flags,
        })
    _unique_index(normalized, "source_record_id", "normalized Stage2 sources")
    return normalized


def plan_stage3_canonical_eligibility(
    canonical_articles: list[dict], source_records: list[dict],
) -> dict:
    """Owner's 2026-11-10 primary journal-article cohort, no corpus deletion.

    Input is *explicitly normalized* source evidence. Each source must specify
    record_family (journal/book/unknown) plus booleans for the three quality
    flags; missing evidence is a contract error, never silently false.
    The source archive itself is immutable and must be kept separately.

    Journal evidence in any canonical member keeps a mixed book+journal group
    eligible, unless *any* member reports retraction. Book-only groups are
    excluded. Unknown-only family requires resolution, not auto-inclusion.
    """
    articles = _unique_index(canonical_articles, "canonical_article_id", "canonical")
    sources = _unique_index(source_records, "source_record_id", "source")
    source_to_article = {}
    for article_id, article in articles.items():
        members = article.get("source_record_ids")
        if not isinstance(members, list) or not members or len(members) != len(set(members)):
            raise Stage3ContractError("invalid canonical source membership")
        for sid in members:
            if sid not in sources or sid in source_to_article:
                raise Stage3ContractError("missing or duplicate canonical source assignment")
            source_to_article[sid] = article_id
    _exact_coverage("Stage3 source member coverage", source_to_article, set(sources))

    flag_names = ("is_retracted", "peer_review_unknown", "wos_nr_cr_mismatch")
    families = {"journal", "book", "unknown"}
    source_flags = Counter()
    article_flags = Counter()
    rows = []
    for article_id, article in sorted(articles.items()):
        members = [sources[sid] for sid in article["source_record_ids"]]
        for member in members:
            if member.get("record_family") not in families:
                raise Stage3ContractError("explicit journal/book/unknown record_family required")
            for flag in flag_names:
                if flag not in member or (member[flag] is not None
                    and type(member[flag]) is not bool):
                    raise Stage3ContractError(
                        f"explicit tri-state source flag required: {flag}")
                # None = not exposed by this source; never record as False.
                source_flags[flag] += int(member[flag] is True)
                if member[flag] is None:
                    source_flags[f"{flag}_not_exposed"] += 1
        has_journal = any(m["record_family"] == "journal" for m in members)
        has_book = any(m["record_family"] == "book" for m in members)
        has_unknown = any(m["record_family"] == "unknown" for m in members)
        flags = {flag: any(m[flag] for m in members) for flag in flag_names}
        if flags["is_retracted"]:
            status, eligible = "excluded_retracted", False
        elif has_journal:
            status, eligible = "eligible_journal", True
        elif has_unknown:
            status, eligible = "requires_family_resolution", False
        else:
            status, eligible = "excluded_book_only", False
        mixed = has_journal and has_book
        article_flags["mixed_book_journal"] += int(mixed)
        article_flags["peer_review_unknown"] += int(flags["peer_review_unknown"])
        article_flags["wos_nr_cr_mismatch"] += int(flags["wos_nr_cr_mismatch"])
        article_flags["retracted"] += int(flags["is_retracted"])
        rows.append({
            "article_id": article_id,
            "source_record_ids": sorted(article["source_record_ids"]),
            "source_evidence": [
                {
                    "source_record_id": member["source_record_id"],
                    "record_family": member["record_family"],
                    "raw_export_sha256": member.get("raw_export_sha256"),
                    "raw_record_ordinal": member.get("raw_record_ordinal"),
                    "is_retracted": member["is_retracted"],
                    "peer_review_unknown": member["peer_review_unknown"],
                    "wos_nr_cr_mismatch": member["wos_nr_cr_mismatch"],
                }
                for member in sorted(members, key=lambda m: m["source_record_id"])
            ],
            "primary_eligible": eligible,
            "eligibility_status": status,
            "has_journal_source": has_journal,
            "has_book_source": has_book,
            "has_unknown_family_source": has_unknown,
            "mixed_book_journal": mixed,
            **flags,
            "access_class": "restricted",
        })
    statuses = Counter(row["eligibility_status"] for row in rows)
    return {
        "article_count": len(rows),
        "source_record_count": len(sources),
        "primary_eligible_count": sum(row["primary_eligible"] for row in rows),
        "eligibility_by_article_id": {
            row["article_id"]: row["primary_eligible"] for row in rows
        },
        "eligibility_status_counts": dict(sorted(statuses.items())),
        "source_flag_counts": dict(sorted(source_flags.items())),
        "canonical_flag_counts": dict(sorted(article_flags.items())),
        "rows": rows,
        "policy": "journal_if_any_exclude_retracted_book_only_flag_unknown",
        "access_class": "restricted",
    }


def plan_text_inputs(
    canonical_articles: list[dict],
    source_records: list[dict],
    source_choice: dict[str, str],
    eligibility: dict[str, bool],
    *,
    permitted_missing_states: set[str],
) -> list[dict]:
    """Require explicit *per-article* scientific choices: never auto-pick a text.

    The returned rows may contain licensed titles/abstracts: private storage only.
    Text hash represents the selected raw fields, not the not-yet-pinned
    PubMedBERT/SPECTER2 tokenizer concatenation.
    """
    articles = _unique_index(canonical_articles, "canonical_article_id", "canonical")
    sources = _unique_index(source_records, "source_record_id", "source")
    ids = set(articles)
    _exact_coverage("eligibility", eligibility, ids)
    _exact_coverage("source choices", source_choice, ids)
    if permitted_missing_states not in (
        {"both", "title_only"}, {"both", "title_only", "abstract_only"},
    ):
        raise Stage3ContractError("owner-approved title-only policy must be allowed")
    out = []
    for article_id in sorted(ids):
        article = articles[article_id]
        selected = source_choice[article_id]
        if not isinstance(eligibility[article_id], bool):
            raise Stage3ContractError("eligibility must be an explicit boolean")
        if selected not in article.get("source_record_ids", []):
            raise Stage3ContractError(f"source choice not in canonical group {article_id}")
        raw = sources.get(selected)
        if raw is None:
            raise Stage3ContractError(f"missing chosen source record {selected}")
        title = raw.get("title") or ""
        abstract = raw.get("abstract") or ""
        if not isinstance(title, str) or not isinstance(abstract, str):
            raise Stage3ContractError("invalid source title/abstract")
        state = ("both" if title.strip() and abstract.strip() else
                 "title_only" if title.strip() else
                 "abstract_only" if abstract.strip() else "missing_both")
        eligible = eligibility[article_id]
        # A title-only vector is valid only if NO source record in this
        # canonical group supplies an abstract. Never discard an existing
        # abstract silently or select between conflicting sources here.
        candidates = []
        for member_id in article["source_record_ids"]:
            member = sources.get(member_id)
            if member is None:
                raise Stage3ContractError(f"unavailable canonical source member {member_id}")
            candidate_abstract = member.get("abstract") or ""
            if not isinstance(candidate_abstract, str):
                raise Stage3ContractError("invalid alternative source abstract")
            if candidate_abstract.strip():
                candidates.append(member_id)
        candidates.sort()
        needs_source_resolution = (
            eligible and state in {"title_only", "missing_both"} and bool(candidates)
        )
        status = ("excluded_by_policy" if not eligible else
                  "requires_source_resolution" if needs_source_resolution else
                  "ready" if state in permitted_missing_states else
                  "missing_input")
        payload = json.dumps([title, abstract], ensure_ascii=False, separators=(",", ":")).encode("utf8")
        out.append({
            "article_id": article_id,
            "source_record_id": selected,
            "source_record_ids": sorted(article["source_record_ids"]),
            "abstract_available_source_record_ids": candidates,
            "text_fields_sha256": sha256(payload).hexdigest(),
            "title": title, "abstract": abstract,
            "text_state": state, "embedding_input_status": status,
            "title_only_vector": (status == "ready" and state == "title_only"),
            "access_class": "restricted",
        })
    return out




def plan_pubmedbert_text_inputs(
    canonical_articles: list[dict], source_records: list[dict],
    eligibility: dict[str, bool],
) -> list[dict]:
    """Entrypoint for the owner-approved deterministic PubMedBERT text policy.

    Other representation families may use their own source selection contracts;
    this entrypoint intentionally cannot accept arbitrary source choices.
    """
    choices = choose_pubmedbert_source_priority(canonical_articles, source_records)
    return plan_text_inputs(
        canonical_articles, source_records, choices, eligibility,
        permitted_missing_states={"both", "title_only"},
    )

def plan_specter2_text_inputs(
    canonical_articles: list[dict], source_records: list[dict],
    eligibility: dict[str, bool],
) -> list[dict]:
    """SPECTER2 owner-approved complete-record-first PubMed > WoS > APA.

    Reuse the same evidence-preserving source choice as PubMedBERT, but not
    PubMedBERT's fragmenting/tokenizer policy. Title-only is valid iff every
    canonical source record lacks an abstract; otherwise expose the conflict.
    """
    choices = choose_pubmedbert_source_priority(canonical_articles, source_records)
    return plan_text_inputs(
        canonical_articles, source_records, choices, eligibility,
        permitted_missing_states={"both", "title_only"},
    )


def summarize_specter2_truncation(
    rows: list[dict], *, canonical_total: int,
) -> dict:
    """Audit pinned-tokenizer counts before/after approved SPECTER2 truncation.

    Each ready article must carry its real full (including specials) token count
    and encoded count. A caller may not claim a full 512-token input was kept if
    it actually lost any tokens. Raw texts stay in restricted input artifacts.
    """
    if type(canonical_total) is not int or canonical_total < 1:
        raise Stage3ContractError("invalid SPECTER2 canonical denominator")
    article_rows = _unique_index(rows, "article_id", "SPECTER2 truncation")
    if len(article_rows) != canonical_total:
        raise Stage3ContractError("SPECTER2 full canonical roster required")
    states = Counter()
    ready = 0
    has_abstract = 0
    truncated_articles = 0
    lost_total = 0
    title_only_ready = 0
    for row in article_rows.values():
        status = row.get("embedding_input_status")
        if status not in {
            "ready", "missing_input", "excluded_by_policy", "requires_source_resolution",
        }:
            raise Stage3ContractError("SPECTER2 invalid input status")
        states[status] += 1
        full = row.get("full_input_token_count")
        encoded = row.get("encoded_token_count")
        lost = row.get("truncated_token_count")
        if status != "ready":
            if any(x is not None for x in (full, encoded, lost)):
                raise Stage3ContractError("SPECTER2 non-ready row cannot claim encoded tokens")
            continue
        if any(type(x) is not int for x in (full, encoded, lost)):
            raise Stage3ContractError("SPECTER2 missing tokenizer-derived token counts")
        if full < 1 or encoded != min(full, 512) or lost != max(0, full - 512):
            raise Stage3ContractError("SPECTER2 silent truncation / token-count mismatch")
        state = row.get("text_state")
        if state not in {"both", "title_only"}:
            raise Stage3ContractError("SPECTER2 ready row missing title")
        if row.get("title_only_vector") is not (state == "title_only"):
            raise Stage3ContractError("SPECTER2 incorrect title-only coverage flag")
        ready += 1
        has_abstract += int(state == "both")
        title_only_ready += int(state == "title_only")
        truncated_articles += int(lost > 0)
        lost_total += lost
    pct = lambda n, d: None if d == 0 else round(n * 100 / d, 4)
    return {
        "canonical_article_count": canonical_total,
        "ready_article_count": ready,
        "ready_with_abstract_count": has_abstract,
        "title_only_ready_count": title_only_ready,
        "truncated_article_count": truncated_articles,
        "truncated_pct_canonical": pct(truncated_articles, canonical_total),
        "truncated_pct_ready": pct(truncated_articles, ready),
        "total_truncated_tokens": lost_total,
        "input_status_counts": dict(sorted(states.items())),
        "token_budget_including_specials": 512,
        "policy": "truncate_512_report_token_loss",
    }


def plan_citation_graph(
    canonical_articles: list[dict],
    source_records: list[dict],
    citation_links: list[dict],
    eligibility: dict[str, bool],
    *,
    graph_policy: dict,
) -> dict:
    """Create an observed candidate graph with complete source evidence pointers.

    No training. Exact DOI links only; APA missing references and ambiguous DOIs
    are not turned into artificial edges. No scientific graph policy is defaulted.
    """
    articles = _unique_index(canonical_articles, "canonical_article_id", "canonical")
    sources = _unique_index(source_records, "source_record_id", "source")
    ids = set(articles)
    _exact_coverage("eligibility", eligibility, ids)
    if any(not isinstance(x, bool) for x in eligibility.values()):
        raise Stage3ContractError("eligibility must be boolean")
    if set(graph_policy) != {"orientation", "duplicate_policy", "self_loop_policy"}:
        raise Stage3ContractError("explicit graph policy required, without hidden defaults")
    if graph_policy["orientation"] not in {"directed", "undirected"}:
        raise Stage3ContractError("graph orientation not approved")
    if graph_policy["duplicate_policy"] not in {"binary", "observation_count"}:
        raise Stage3ContractError("graph duplication policy not approved")
    if graph_policy["self_loop_policy"] not in {"retain", "exclude"}:
        raise Stage3ContractError("self-loop policy not approved")
    source_to_article: dict[str, str] = {}
    for article_id, article in articles.items():
        for sid in article.get("source_record_ids", []):
            if sid in source_to_article or sid not in sources:
                raise Stage3ContractError("duplicate/missing source member")
            source_to_article[sid] = article_id
    if set(source_to_article) != set(sources):
        raise Stage3ContractError("source mapping incomplete")
    status_counts = Counter()
    excluded_edges = Counter()
    edges = Counter()
    evidence_by_edge: dict[tuple[str, str], list[dict]] = {}
    seen_refs: set[tuple[str, int]] = set()
    for link in citation_links:
        status = link.get("resolution_method")
        if status not in ALLOWED_REFERENCE_STATUS:
            raise Stage3ContractError("unknown citation-resolution status")
        status_counts[status] += 1
        source_id = link.get("citing_source_record_id")
        if source_id not in source_to_article:
            raise Stage3ContractError("citing record has no canonical article")
        source = sources[source_id]
        ordinal = link.get("raw_reference_ordinal")
        pointer = link.get("raw_evidence_pointer")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
            raise Stage3ContractError("invalid raw reference ordinal")
        if (not isinstance(pointer, dict)
            or pointer.get("export_sha256") != source.get("raw_export_sha256")
            or not SHA256.fullmatch(str(pointer.get("export_sha256", "")))
            or pointer.get("record_ordinal") != source.get("raw_record_ordinal")
            or pointer.get("reference_ordinal") != ordinal):
            raise Stage3ContractError("citation source provenance does not match original record")
        references = source.get("cited_references_raw")
        if not isinstance(references, list) or ordinal > len(references):
            raise Stage3ContractError("citation is not observed in source reference list")
        if source.get("reference_coverage") == "not_exposed":
            raise Stage3ContractError("fabricated reference from not_exposed source")
        key = (source_id, ordinal)
        if key in seen_refs:
            raise Stage3ContractError("duplicate source reference identity")
        seen_refs.add(key)
        target = link.get("cited_article_id")
        if status != "exact_doi":
            if target is not None:
                raise Stage3ContractError("unresolved/ambiguous citation has invented target")
            continue
        if target is None or target not in articles:
            raise Stage3ContractError("exact DOI target not present in frozen article roster")
        source_article = source_to_article[source_id]
        if not eligibility[source_article] or not eligibility[target]:
            excluded_edges["excluded_policy"] += 1
            continue
        if source_article == target and graph_policy["self_loop_policy"] == "exclude":
            excluded_edges["self_loop_policy"] += 1
            continue
        pair = (source_article, target)
        if graph_policy["orientation"] == "undirected":
            pair = tuple(sorted(pair))
        edges[pair] += 1
        evidence_by_edge.setdefault(pair, []).append({
            "source_record_id": source_id,
            "raw_reference_ordinal": ordinal,
            "export_sha256": pointer["export_sha256"],
            "record_ordinal": pointer["record_ordinal"],
        })
    rows = [
        {"source_article_id": left, "target_article_id": right,
         "observation_count": count,
         "weight": count if graph_policy["duplicate_policy"] == "observation_count" else 1,
         "evidence_pointers": sorted(evidence_by_edge[(left, right)],
             key=lambda p: (p["source_record_id"], p["raw_reference_ordinal"]))}
        for (left, right), count in sorted(edges.items())
    ]
    adjacent: set[str] = set()
    for left, right in edges:
        adjacent.update((left, right))
    node_rows = []
    for article_id, article in sorted(articles.items()):
        coverage = sorted({
            sources[sid].get("reference_coverage", "unknown")
            for sid in article["source_record_ids"]
        })
        observed = article_id in adjacent
        outgoing_observed = any(s in ("exposed", "incomplete") for s in coverage)
        node_rows.append({
            "article_id": article_id,
            "eligible": eligibility[article_id],
            "reference_coverage": coverage,
            "has_observed_resolved_edge": observed,
            "isolate_reason": (None if observed else
                "excluded_by_policy" if not eligibility[article_id] else
                "missing_reference_coverage" if not outgoing_observed else
                "no_resolved_observed_edge"),
        })
    return {
        "article_count": len(ids),
        "eligible_article_count": sum(eligibility.values()),
        "citation_status_counts": dict(sorted(status_counts.items())),
        "excluded_edge_observations": dict(sorted(excluded_edges.items())),
        "graph_policy": dict(graph_policy),
        "nodes": node_rows,
        "edges": rows,
        "edge_count": len(rows),
        "edge_observation_count": sum(edges.values()),
        "access_class": "restricted",
    }


def plan_approved_node2vec_graph(
    canonical_articles: list[dict], source_records: list[dict],
    citation_links: list[dict], eligibility: dict[str, bool],
) -> dict:
    """Make two verifiable projections: original directed citations and
    owner-approved binary undirected node2vec training edges.

    Uses observed exact-DOI links only, deduplicates repeated source records,
    and excludes self-citations in the training projection. Never infers
    unobserved references or changes the directed evidence graph.
    """
    directed_policy = {
        "orientation": "directed", "duplicate_policy": "binary",
        # Preserve every observed exact-DOI link, including self-citations,
        # in the original directed evidence network.
        "self_loop_policy": "retain",
    }
    walk_policy = {
        "orientation": "undirected", "duplicate_policy": "binary",
        "self_loop_policy": "exclude",
    }
    # Original resolved citation evidence includes excluded/non-eligible papers:
    # only the derived node2vec training graph applies primary cohort filtering.
    all_source_nodes = {
        article["canonical_article_id"]: True for article in canonical_articles
    }
    directed = plan_citation_graph(
        canonical_articles, source_records, citation_links, all_source_nodes,
        graph_policy=directed_policy,
    )
    training = plan_citation_graph(
        canonical_articles, source_records, citation_links, eligibility,
        graph_policy=walk_policy,
    )
    excluded = training["excluded_edge_observations"]
    if (directed["edge_observation_count"] !=
        training["edge_observation_count"] +
        excluded.get("self_loop_policy", 0) +
        excluded.get("excluded_policy", 0)):
        raise Stage3ContractError("node2vec graph projection lost citation observations")
    if any(edge["weight"] != 1 for edge in training["edges"]):
        raise Stage3ContractError("node2vec training graph must use unit weights")
    return {
        "directed_citation_graph": directed,
        "node2vec_training_graph": training,
        "node2vec_isolate_vector_status": "missing_structural",
        "training_graph_orientation": "undirected",
        "source_graph_orientation": "directed",
    }


def validate_vector_rows(
    canonical_article_ids: list[str], vector_rows: list[dict], *,
    dimension: int, model_identity_hash: str
) -> dict:
    """Ensure missing inputs are explicit, never replaced by fabricated zeros."""
    if not isinstance(dimension, int) or dimension < 1:
        raise Stage3ContractError("invalid embedding dimension")
    if not SHA256.fullmatch(model_identity_hash):
        raise Stage3ContractError("model identity missing")
    if len(set(canonical_article_ids)) != len(canonical_article_ids):
        raise Stage3ContractError("duplicate canonical roster")
    rows = _unique_index(vector_rows, "article_id", "vectors")
    _exact_coverage("vector roster including missing statuses", rows, set(canonical_article_ids))
    counts = Counter()
    for row in vector_rows:
        state = row.get("status")
        if state not in {"present", "missing_input", "missing_structural", "excluded_by_policy"}:
            raise Stage3ContractError("unknown vector status")
        counts[state] += 1
        if row.get("model_identity_hash") != model_identity_hash:
            raise Stage3ContractError("model identity drift")
        vector = row.get("vector")
        if state != "present":
            if vector is not None:
                raise Stage3ContractError("missing vector must be null, not a fake value")
            continue
        if not isinstance(vector, (list, tuple)) or len(vector) != dimension:
            raise Stage3ContractError("embedding has wrong dimension")
        if any(not isinstance(value, (int, float)) or isinstance(value, bool)
               or not math.isfinite(value) for value in vector):
            raise Stage3ContractError("embedding contains invalid/nonfinite values")
    return {"article_count": len(rows), "dimension": dimension,
            "status_counts": dict(sorted(counts.items())),
            "model_identity_hash": model_identity_hash}


def aggregate_weighted_fragments(fragments: list[dict], *, dimension: int) -> list[float]:
    """Owner-selected B: combine CLS *or* mean fragment vectors by content token count.

    Each fragment must count only genuine (non-special, non-padding) tokens.
    The list must cover the selected article input *once*, with no gaps/overlap;
    the caller supplies fragment-local vectors from the last hidden layer.
    This is not a claim of equivalence to a >512-token transformer context.
    """
    if not isinstance(dimension, int) or isinstance(dimension, bool) or dimension <= 0:
        raise Stage3ContractError("invalid dimension")
    if not fragments:
        raise Stage3ContractError("missing fragments")
    numerator = [0.0] * dimension
    total = 0
    expected_start = 0
    for chunk in fragments:
        start, end = chunk.get("content_start"), chunk.get("content_end")
        n = chunk.get("content_token_count")
        if any(not isinstance(x, int) or isinstance(x, bool) for x in (start, end, n)):
            raise Stage3ContractError("invalid fragment offsets/count")
        if start != expected_start or end <= start or end - start != n:
            raise Stage3ContractError("fragment gap, overlap or token-count mismatch")
        input_len = chunk.get("input_token_count")
        if (not isinstance(input_len, int) or isinstance(input_len, bool)
            or input_len < n or input_len > 512):
            raise Stage3ContractError("fragment exceeds model limit or invalid token count")
        vector = chunk.get("vector")
        if (not isinstance(vector, (list, tuple)) or len(vector) != dimension
            or any(isinstance(x, bool) or not isinstance(x, (int, float))
                   or not math.isfinite(x) for x in vector)):
            raise Stage3ContractError("invalid fragment vector")
        for k, value in enumerate(vector):
            numerator[k] += value * n
        total += n
        expected_start = end
    if total <= 0:
        raise Stage3ContractError("no content tokens")
    result = [value / total for value in numerator]
    if not all(math.isfinite(x) for x in result):
        raise Stage3ContractError("invalid aggregate")
    return result


def summarize_long_abstract_coverage(rows: list[dict], *, canonical_total: int) -> dict:
    """Aggregate no-text metrics after tokenizer-aware chunking; no raw text output.

    Exact threshold is whether the pinned tokenizer yields >512 tokens for the
    owner-approved full title+separator+abstract input, including special tokens.
    Excluded/missing articles are represented explicitly, never silently dropped.
    """
    if not isinstance(canonical_total, int) or canonical_total < 1:
        raise Stage3ContractError("invalid canonical denominator")
    roster = _unique_index(rows, "article_id", "long-abstract coverage")
    if len(roster) != canonical_total:
        raise Stage3ContractError("full canonical roster required for denominator")
    eligible = 0
    has_abstract = 0
    long_abstract = 0
    chunked = 0
    chunked_with_abstract = 0
    forced_sentence_splits = 0
    chunk_histogram = Counter()
    for row in rows:
        if not isinstance(row.get("eligible"), bool):
            raise Stage3ContractError("missing eligibility status")
        if not isinstance(row.get("has_abstract"), bool):
            raise Stage3ContractError("missing abstract availability")
        n = row.get("fragment_count")
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise Stage3ContractError("invalid fragment count")
        exceeds = row.get("full_input_exceeds_512")
        if not isinstance(exceeds, bool):
            raise Stage3ContractError("missing pinned tokenizer length threshold")
        abstract_exceeds = row.get("abstract_tokens_exceeds_512")
        if not isinstance(abstract_exceeds, bool):
            raise Stage3ContractError("missing abstract-only token length threshold")
        if abstract_exceeds and not row["has_abstract"]:
            raise Stage3ContractError("long abstract marked for missing abstract")
        if abstract_exceeds and not exceeds:
            raise Stage3ContractError("abstract exceeds limit but full input does not")
        forced = row.get("forced_sentence_splits")
        if not isinstance(forced, int) or isinstance(forced, bool) or forced < 0:
            raise Stage3ContractError("invalid forced sentence split count")
        if not row["eligible"] and (n or exceeds or forced):
            raise Stage3ContractError("excluded article cannot count as processed")
        if row["eligible"]:
            eligible += 1
            has_abstract += int(row["has_abstract"])
            long_abstract += int(abstract_exceeds)
            if n < 1:
                raise Stage3ContractError("eligible article has no processed input")
            if (n > 1) != exceeds:
                raise Stage3ContractError("chunk count must match input-overflow flag")
            if forced and n < 2:
                raise Stage3ContractError("forced split without multiple fragments")
            if not row.get("full_content_covered"):
                raise Stage3ContractError("truncated or untracked content")
            chunked += int(exceeds)
            chunked_with_abstract += int(exceeds and row["has_abstract"])
            forced_sentence_splits += forced
            chunk_histogram[str(n)] += 1
    pct = lambda num, denom: None if denom == 0 else round(100.0 * num / denom, 4)
    return {
        "canonical_article_count": canonical_total,
        "eligible_text_article_count": eligible,
        "eligible_with_abstract_count": has_abstract,
        "abstract_itself_over_512_count": long_abstract,
        "pct_abstract_itself_over_512_of_canonical": pct(long_abstract, canonical_total),
        "pct_abstract_itself_over_512_of_eligible_abstracts": pct(long_abstract, has_abstract),
        "articles_needing_fragments": chunked,
        "chunked_articles_with_abstract_count": chunked_with_abstract,
        "pct_all_canonical": pct(chunked, canonical_total),
        "pct_eligible_text": pct(chunked, eligible),
        "pct_eligible_with_abstract": pct(chunked_with_abstract, has_abstract),
        "forced_sentence_splits_total": forced_sentence_splits,
        "fragment_count_histogram": dict(sorted(chunk_histogram.items(), key=lambda kv: int(kv[0]))),
        "status": "descriptive_postprocessing_report_not_a_method_selection",
    }


def pack_sentence_token_groups(
    sentence_token_ids: list[list[int]], *,
    first_content_capacity: int,
    subsequent_content_capacity: int,
) -> dict:
    """Greedy sentence-aware packing of ALREADY tokenized abstract sentences.

    The caller reserves the 512-token model overhead (CLS/SEP and the title
    where present) in both capacities; title is represented once in the first
    chunk and must be included separately by the caller. No overlap or text
    drop. If one sentence cannot fit a fresh chunk, split it by token count.
    Re-check the final *model-encoded* total length <=512 at the model boundary.
    """
    if not sentence_token_ids:
        return {"chunks": [], "forced_sentence_splits": 0}
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 1
           for n in (first_content_capacity, subsequent_content_capacity)):
        raise Stage3ContractError("invalid tokenizer chunk capacity")
    if any(not isinstance(x, list) or not x
           or any(not isinstance(t, int) or isinstance(t, bool) or t < 0 for t in x)
           for x in sentence_token_ids):
        raise Stage3ContractError("sentence token groups must contain token IDs")
    chunks: list[list[int]] = []
    buf: list[int] = []
    forced = 0
    for sentence in sentence_token_ids:
        remaining = list(sentence)
        did_split = False
        while remaining:
            limit = first_content_capacity if not chunks else subsequent_content_capacity
            room = limit - len(buf)
            if room <= 0:
                chunks.append(buf)
                buf = []
                continue
            if len(remaining) <= room:
                buf.extend(remaining)
                remaining = []
                continue
            if buf:
                # Preserve a sentence boundary by starting a fresh chunk.
                chunks.append(buf)
                buf = []
                continue
            # Oversized single sentence: split at tokenizer boundaries, not
            # silently discard its tail. Count one forced split per sentence.
            if not did_split:
                forced += 1
                did_split = True
            buf.extend(remaining[:room])
            remaining = remaining[room:]
            chunks.append(buf)
            buf = []
    if buf:
        chunks.append(buf)
    expected = [t for sentence in sentence_token_ids for t in sentence]
    actual = [t for chunk in chunks for t in chunk]
    if actual != expected:
        raise Stage3ContractError("token loss or duplication during sentence packing")
    for idx, chunk in enumerate(chunks):
        limit = first_content_capacity if idx == 0 else subsequent_content_capacity
        if not chunk or len(chunk) > limit:
            raise Stage3ContractError("packed chunk overflow")
    return {"chunks": chunks, "forced_sentence_splits": forced}

def mean_pooling_content_mask(
    attention_mask: list[int], special_tokens_mask: list[int]
) -> list[int]:
    """Select text tokens only for PubMedBERT masked mean (owner-approved).

    1 marks real content, 0 marks all special/padding tokens. The tokenizer must
    supply a special_tokens_mask for the final encoded input including CLS/SEP.
    CLS-branch output remains independent and uses the last hidden CLS vector.
    """
    if (not isinstance(attention_mask, list)
        or not isinstance(special_tokens_mask, list)
        or not attention_mask
        or len(attention_mask) != len(special_tokens_mask)):
        raise Stage3ContractError("invalid content/special token masks")
    if any(type(x) is not int or x not in (0, 1)
           for x in attention_mask + special_tokens_mask):
        raise Stage3ContractError("nonbinary token masks")
    result = [
        int(attended == 1 and special == 0)
        for attended, special in zip(attention_mask, special_tokens_mask)
    ]
    if not any(result):
        raise Stage3ContractError("no content tokens for mean pooling")
    return result



def summarize_pubmedbert_text_coverage(rows: list[dict], *, canonical_total: int) -> dict:
    """Report owner-approved title-only coverage after source reconciliation.

    Do not invent a title, infer an abstract, or label an unresolved alternate
    abstract as title-only. No raw bibliographic text is returned.
    """
    if not isinstance(canonical_total, int) or isinstance(canonical_total, bool) or canonical_total < 1:
        raise Stage3ContractError("invalid canonical denominator")
    indexed = _unique_index(rows, "article_id", "PubMedBERT text coverage")
    if len(indexed) != canonical_total:
        raise Stage3ContractError("full canonical roster required")
    statuses = Counter()
    states = Counter()
    title_only = 0
    eligible = 0
    ready = 0
    for row in rows:
        status = row.get("embedding_input_status")
        state = row.get("text_state")
        if status not in {
            "ready", "missing_input", "excluded_by_policy", "requires_source_resolution"
        } or state not in {"both", "title_only", "abstract_only", "missing_both"}:
            raise Stage3ContractError("unrecognized text coverage status")
        flagged = row.get("title_only_vector")
        if type(flagged) is not bool:
            raise Stage3ContractError("missing explicit title-only flag")
        if flagged != (status == "ready" and state == "title_only"):
            raise Stage3ContractError("incorrect title-only status")
        candidates = row.get("abstract_available_source_record_ids")
        if not isinstance(candidates, list) or any(not isinstance(c, str) for c in candidates):
            raise Stage3ContractError("invalid abstract provenance candidates")
        if flagged and candidates:
            raise Stage3ContractError("title-only assigned while abstract available")
        statuses[status] += 1
        states[state] += 1
        eligible += int(status != "excluded_by_policy")
        ready += int(status == "ready")
        title_only += int(flagged)
    pct = lambda n, d: None if d == 0 else round(100 * n / d, 4)
    return {
        "canonical_article_count": canonical_total,
        "eligible_article_count": eligible,
        "ready_text_article_count": ready,
        "title_only_count": title_only,
        "title_only_pct_canonical": pct(title_only, canonical_total),
        "title_only_pct_eligible": pct(title_only, eligible),
        "title_only_pct_ready": pct(title_only, ready),
        "state_counts": dict(sorted(states.items())),
        "status_counts": dict(sorted(statuses.items())),
        "title_only_policy": "preserve_and_flag_do_not_penalize",
    }


def preserve_raw_and_l2_article_vector(
    raw_article_vector: list[float], *, dimension: int = 768,
) -> dict:
    """Preserve owner-approved final raw vector and norm; normalize only afterward.

    raw_article_vector must be the final CLS or masked-mean article vector,
    i.e. after token-weighted fragment aggregation, before L2 normalization.
    No token-level hidden states, weight training or corpus reads here.
    """
    if not isinstance(dimension, int) or isinstance(dimension, bool) or dimension < 1:
        raise Stage3ContractError("invalid article-vector dimension")
    if (not isinstance(raw_article_vector, (tuple, list))
        or len(raw_article_vector) != dimension
        or any(isinstance(v, bool) or not isinstance(v, (float, int))
               or not math.isfinite(v) for v in raw_article_vector)):
        raise Stage3ContractError("raw article vector invalid/nonfinite/dimension mismatch")
    # math.hypot avoids intermediate squared-value overflow.
    norm = math.hypot(*raw_article_vector)
    if not math.isfinite(norm) or norm <= 1e-12:
        raise Stage3ContractError("cannot L2-normalize a near-zero/nonfinite vector")
    unit = [float(x / norm) for x in raw_article_vector]
    if not all(math.isfinite(x) for x in unit):
        raise Stage3ContractError("invalid normalized vector")
    # Keep original input values rather than overwrite them in-place.
    return {
        "raw_article_vector": list(raw_article_vector),
        "raw_l2_norm": norm,
        "unit_article_vector": unit,
        "normalization": "l2_after_article_aggregation",
        "similarity_metric": "cosine",
    }

def preserve_node2vec_article_vector(
    raw_article_vector: list[float],
) -> dict:
    """Retain learned raw node2vec vector and norm, then L2/cosine copy."""
    result = preserve_raw_and_l2_article_vector(
        raw_article_vector, dimension=128,
    )
    result["normalization"] = "l2_after_training"
    return result



def preserve_specter2_article_vector(
    raw_article_vector: list[float],
) -> dict:
    """Retain 768d post-adapter first-token embedding before L2/cosine."""
    result = preserve_raw_and_l2_article_vector(
        raw_article_vector, dimension=768,
    )
    result["normalization"] = "l2_after_final_article_vector"
    return result
