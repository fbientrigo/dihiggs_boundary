#!/usr/bin/env python3

# This script validates all json files in this repository against the
# appropriate json schemas.

import jsonschema
import json
import urllib.request
import sys
from pathlib import Path

validator = jsonschema.Draft7Validator(
    json.load(
        urllib.request.urlopen(
            "https://gitlab.com/higgsbounds/higgstools/-/raw/develop/json/LimitConditional.schema.json"
        )
    )
)


status = 0
ids = {}
for jsonfile in Path(".").rglob("*.json"):
    with open(jsonfile, "r") as j:
        data = json.load(j)

    id = data["id"]
    if id in ids:
        print("\n --> duplicate limit id {} ({} and {})".format(id, jsonfile, ids[id]))
        status = 1
    ids[id] = jsonfile

    try:
        validator.validate(data)
    except jsonschema.ValidationError as error:
        print("\n --> Validation failed on `{}`:".format(jsonfile))
        msg = error.__str__()
        if len(msg) > 10000:
            print(msg[:10000])
        else:
            print(msg)
        status = 1

sys.exit(status)
