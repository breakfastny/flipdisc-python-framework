import os
import sys
import json

from jsonschema import Draft4Validator, validate as validate_schema

HERE = os.path.dirname(os.path.abspath(__file__))

__all__ = ['validate', 'export_settings']


def open_schema(schema_name):
    return open(os.path.join(HERE, schema_name))


def read_schema(schema_name, check=True):
    raw = json.load(open_schema(schema_name))
    if check:
        Draft4Validator.check_schema(raw)
    return raw


def validate(manifest):
    """
    Validate an instance of the userapp.json schema.

    manifest can be a dict object (returned as is) or a filename.
    """
    if isinstance(manifest, str):
        manifest = json.load(open(manifest))
    validate_schema(manifest, read_schema('userapp.json'))
    return manifest


def export_settings(manifest):
    """
    Return a dict with settings extracted from a manifest dict.
    The string "<NO_DEFAULT>" is used for entries without default values.
    """
    config = {}
    for entry in manifest['settings']:
        if 'settings' in entry:
            # Nested settings.
            config[entry['name']] = export_settings(entry)
        else:
            config[entry['name']] = entry.get('default', '<NO_DEFAULT>')

    return config


if __name__ == "__main__":
    result = export_settings(validate(sys.argv[1]))
    print(json.dumps({"settings": result}, indent=4))
