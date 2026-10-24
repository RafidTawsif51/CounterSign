"""The README, the schemas and the code must use the same words. Apify's quality score reads all of them."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()
INPUT = json.loads((ROOT / ".actor" / "input_schema.json").read_text())
DATASET = json.loads((ROOT / ".actor" / "dataset_schema.json").read_text())
ACTOR = json.loads((ROOT / ".actor" / "actor.json").read_text())
OUTPUT = json.loads((ROOT / ".actor" / "output_schema.json").read_text())


def test_readme_has_the_sections_a_store_page_needs_and_enough_words():
    headings = set(re.findall(r"^#{2,3} (.+)$", README, re.M))
    for needed in ("What it does and why", "Who it is for", "How it works", "Input", "Example input", "Output", "Example output", "Confidence rules",
                   "Pricing and cost", "Integrations and scheduling", "FAQ", "Limitations", "Privacy", "Python", "cURL", "Support"):
        assert needed in headings, needed
    assert len(README.split()) >= 1000


def test_every_input_field_is_described_and_in_the_readme():
    for name, field in INPUT["properties"].items():
        assert field.get("title") and len(field.get("description", "")) > 40 and "example" in field, name
        assert f"`{name}`" in README, f"{name} is not in the README"
    assert INPUT["required"] == ["businesses"] and INPUT["properties"]["businesses"]["default"] == INPUT["properties"]["businesses"]["prefill"]


def test_every_output_field_is_described_and_in_the_readme_and_the_example():
    fields = DATASET["fields"]["properties"]
    example = json.loads(re.search(r"### Example output.*?```json\n(.*?)\n```", README, re.S).group(1))
    assert list(example) == list(fields)  # same fields, same order, in the README example and in the dataset schema
    for name, field in fields.items():
        assert field.get("title") or name == "phones" or field.get("description"), name
        assert field.get("description"), name
        assert f"`{name}`" in README, f"{name} is not in the README"
    assert "overview" in DATASET["views"] and DATASET["views"]["overview"]["display"]["component"] == "table"
    assert "apiDefaultDatasetUrl" in OUTPUT["properties"]["results"]["template"]


def test_the_vocabulary_matches_everywhere():
    props = DATASET["fields"]["properties"]
    found_in = set(props["phones"]["items"]["properties"]["sources"]["items"]["properties"]["found_in"]["enum"])
    for word in found_in | set(props["agreement"]["enum"]) | set(props["confidence"]["enum"]):
        assert f"`{word}`" in README, word
    from src.assess import AGREEMENT, CONFIDENCE
    from src.phones import FOUND_IN

    assert found_in == set(FOUND_IN) and set(props["agreement"]["enum"]) == set(AGREEMENT) and set(props["confidence"]["enum"]) == set(CONFIDENCE)


def test_the_readme_examples_are_real_rows_and_valid_json():
    blocks = re.findall(r"```json\n(.*?)\n```", README, re.S)
    assert len(blocks) >= 3
    for block in blocks:
        json.loads(block)
    default = json.loads(blocks[0])  # example input
    assert default["businesses"] == INPUT["properties"]["businesses"]["default"]
    assert default["businesses"][0]["website_url"].startswith("https://aayushswami123.github.io/Countersign/summit-concrete/")


def test_actor_json_is_complete_and_the_title_and_name_agree():
    assert ACTOR["title"] == "Vendor Contact Verifier" and README.startswith("# Vendor Contact Verifier")
    assert 50 <= len(ACTOR["description"]) <= 300 and ACTOR["categories"]
    for key in ("input", "output", "readme", "changelog"):
        assert (ROOT / ".actor" / ACTOR[key]).resolve().is_file(), key
    assert (ROOT / ".actor" / ACTOR["storages"]["dataset"]).is_file()


def test_no_em_dashes_anywhere_in_the_docs():
    for f in [ROOT / "README.md", ROOT / "CHANGELOG.md", *(ROOT / ".actor").glob("*.json")]:
        assert "—" not in f.read_text(), f
