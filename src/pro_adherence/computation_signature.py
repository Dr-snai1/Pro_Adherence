"""Stage 0 immutable model identity and computation signature validation."""
import hashlib
import json
import re

SHA = re.compile(r"^[0-9a-f]{64}$")
MUTABLE_VERSION_ALIASES = {
    "latest", "current", "head", "main", "master", "tip",
    "trunk", "default", "stable", "newest",
}

class SignatureError(ValueError):
    pass

def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

def hash_descriptor(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def model_descriptor(model):
    digest = model.get("digest")
    revision = model.get("immutable_revision")
    namespace = model.get("identity_namespace")
    key = model.get("identity_key")
    if digest is not None and (not isinstance(digest, str) or not SHA.fullmatch(digest)):
        raise SignatureError("digest must be lowercase sha256")
    if revision is not None and (not isinstance(revision, str) or not revision):
        raise SignatureError("invalid immutable revision")
    if isinstance(revision, str) and revision.casefold() in MUTABLE_VERSION_ALIASES:
        raise SignatureError("mutable model revision alias is forbidden")
    if digest is None and revision is None:
        raise SignatureError("no immutable model identity")
    if revision is not None and (not namespace or not key):
        raise SignatureError("revision requires namespace and key")
    if namespace is not None and (not isinstance(namespace, str) or not namespace):
        raise SignatureError("invalid namespace")
    if key is not None and (not isinstance(key, str) or not key):
        raise SignatureError("invalid key")
    return {"identity_schema":"model-identity/v1", "content_digest":digest,
            "identity_namespace":namespace, "identity_key":key,
            "immutable_revision":revision}

def model_identity_hash(model):
    return hash_descriptor(model_descriptor(model))

def computation_digest(signature):
    fields = ("input_artifact_hashes", "code_ref_id", "config_hash",
              "model_identity_hash", "schema_version")
    preimage = {k:signature[k] for k in fields}
    if not preimage["input_artifact_hashes"] or any(not isinstance(v,str) or not SHA.fullmatch(v) for v in preimage["input_artifact_hashes"]):
        raise SignatureError("invalid input hashes")
    if not SHA.fullmatch(preimage["config_hash"]):
        raise SignatureError("invalid config hash")
    h=preimage["model_identity_hash"]
    if h is not None and (not isinstance(h,str) or not SHA.fullmatch(h)):
        raise SignatureError("invalid identity hash")
    return hash_descriptor(preimage)

def validate_compute_asset(asset, models, artifacts=None, configs=None):
    if "model_ref_id" not in asset:
        raise SignatureError("missing model_ref_id")
    ref=asset["model_ref_id"]
    index={x["model_ref_id"]:x for x in models}
    if ref is not None and ref not in index:
        raise SignatureError("unresolved model_ref_id")
    expected=None if ref is None else model_identity_hash(index[ref])
    signature=asset["computation_signature"]
    if "model_identity_hash" not in signature or signature["model_identity_hash"] != expected:
        raise SignatureError("identity mismatch")
    if signature["code_ref_id"] != asset["code_ref_id"]:
        raise SignatureError("code ref mismatch")
    if artifacts is not None:
        artifact_index={x["artifact_id"]:x["content_hash"] for x in artifacts}
        try:
            input_hashes=[artifact_index[x] for x in asset["input_artifact_ids"]]
        except KeyError as e:
            raise SignatureError("unresolved artifact") from e
        if signature["input_artifact_hashes"] != input_hashes:
            raise SignatureError("input hashes mismatch")
    if configs is not None:
        config_index={x["config_ref_id"]:x["content_hash"] for x in configs}
        if config_index.get(asset["config_ref_id"]) != signature["config_hash"]:
            raise SignatureError("config hash mismatch")
    if signature["digest"] != computation_digest(signature):
        raise SignatureError("computation digest mismatch")
    return True
