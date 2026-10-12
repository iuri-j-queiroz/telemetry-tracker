"""JSON schema for the envelope. See agent.md, section 3."""

from jsonschema import Draft202012Validator

ENVELOPE_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["kind"],
    "properties": {
        "kind": {"type": "string", "minLength": 1},
        "x": {
            "type": "object",
            "required": ["values"],
            "properties": {
                "name": {"type": "string"},
                "unit": {"type": "string"},
                "values": {"type": "array"},
            },
        },
        "series": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label"],
                "properties": {
                    "label": {"type": "string"},
                    "color": {"type": "string"},
                    "values": {"type": "array"},
                    "x": {"type": "array"},
                    "y": {"type": "array"},
                },
            },
        },
        "meta": {"type": "object"},
        "data_base64": {"type": "string"},
        "mime": {"type": "string"},
    },
    "anyOf": [{"required": ["series"]}, {"required": ["data_base64"]}],
}

_VALIDATOR = Draft202012Validator(ENVELOPE_SCHEMA)


def validate_envelope(data) -> list[str]:
    """Return a list of schema errors. An empty list means the envelope is valid."""
    if not isinstance(data, dict):
        return ["envelope must be a JSON object"]
    errors = []
    for error in sorted(_VALIDATOR.iter_errors(data), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in error.absolute_path)
        errors.append(f"{path}: {error.message}" if path else error.message)
    return errors
