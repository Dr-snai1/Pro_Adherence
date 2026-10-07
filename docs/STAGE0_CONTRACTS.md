# Stage 0 contracts — IDs, entities, access/license

Status: implemented, developer-checked; independent QA pending.

## Internal IDs

Internal surrogate identifiers use canonical lowercase UUIDv7. They do not encode scientific meaning or provider identity. External identifiers such as DOI, PMID, ORCID and ROR remain separate fields/namespaces.

The exception is `source_id`, which is a stable provider key because the source entity is the provider itself (for example `pubmed` or `apa_psycinfo`).

## Entity contract

`contracts/schemas/entities.schema.json` implements the entity fields fixed by TECHNICAL_ARCHITECTURE §§3.2–3.6: article, article external ID, source record, author, authorship, affiliation, author-affiliation, source, venue and citation edge.

Source and venue are distinct entities. Authorship and author-affiliation preserve original source strings and source-record provenance. Citation edges distinguish a resolved canonical target from an external unresolved target.

## Access / license

The four architectural access classes are fixed exactly as: `public`, `project-internal`, `restricted-license`, `secret`.

Actual legal license classes are deliberately not invented by implementation. `license_class` is an explicit provider/project-defined value with evidence and a status. Publication permissions are explicit for metadata, raw text and derived outputs.

Default is deny: an unknown license status cannot allow raw-text publication; `secret` denies all publication; the policy registry requires access class `public` for promotion to the public bundle.

This implements, rather than replaces, TECHNICAL_ARCHITECTURE. Artifact/run/provenance and release-manifest contracts are separate Stage 0 iterations.
