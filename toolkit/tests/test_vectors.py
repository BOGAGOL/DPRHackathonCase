import copy
import json
from pathlib import Path

import pytest

from dprcrypto import CryptoError
from dprcrypto import vectors


ROOT = Path(__file__).resolve().parents[2]


def test_shared_vector_file_and_corrupted_expectation():
    document = json.loads((ROOT / "docs/contracts/test_vectors.json").read_text(encoding="utf-8"))
    assert all(vectors.verify_document(document).values())
    corrupt = copy.deepcopy(document)
    corrupt["blind_index"]["cases"][0]["bidx_hex"] = "incorrect"
    assert not vectors.verify_document(corrupt)["bidx"]
    document["test_only"] = False
    with pytest.raises(CryptoError):
        vectors.verify_document(document)


def test_generator_is_synthetic_exclusive_and_cli_writes_evidence(tmp_path, monkeypatch, capsys):
    path, evidence = tmp_path / "vectors.json", tmp_path / "evidence.json"
    monkeypatch.setattr("sys.argv", ["vectors", "generate", "--vectors", str(path)])
    vectors.main()
    with pytest.raises(FileExistsError):
        vectors.generate_file(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["test_only"] and len(document["fields"]) == 6
    monkeypatch.setattr("sys.argv", ["vectors", "verify", "--vectors", str(path), "--evidence", str(evidence)])
    vectors.main()
    assert json.loads(evidence.read_text())["passed"]
    output = capsys.readouterr().out
    assert all(item["dek_hex"] not in output for item in document["fields"])
    path.write_text("{}")
    with pytest.raises(SystemExit):
        vectors.main()
    assert not json.loads(evidence.read_text())["passed"]
