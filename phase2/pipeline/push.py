"""
HuggingFace Hub push layer
Uploads the final dataset to notvcto/zero-dataset as a public HF dataset.
Requires: HF_TOKEN
"""

import os
import json
import logging
from pathlib import Path
from datasets import Dataset, DatasetDict
from huggingface_hub import HfApi

log = logging.getLogger(__name__)

HF_REPO = "notvcto/zero-dataset"


def push(jsonl_path: str, token: str | None = None) -> str:
    """
    Load the JSONL file, push to HF Hub as a Dataset.
    Returns the repo URL.
    """
    token = token or os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN not set")

    # Load JSONL
    records = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    log.info(f"loaded {len(records)} records from {jsonl_path}")

    # Convert to HF Dataset
    dataset = Dataset.from_list(records)

    # Split: 95% train, 5% test (held out for eval)
    split = dataset.train_test_split(test_size=0.05, seed=42)
    dataset_dict = DatasetDict({
        "train": split["train"],
        "test": split["test"],
    })

    log.info(f"pushing to {HF_REPO}...")
    dataset_dict.push_to_hub(
        HF_REPO,
        token=token,
        commit_message=f"Add seed dataset ({len(records)} triples)",
        private=False,
    )

    url = f"https://huggingface.co/datasets/{HF_REPO}"
    log.info(f"pushed: {url}")
    return url


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/seed.jsonl"
    url = push(path)
    print(f"Dataset live at: {url}")
