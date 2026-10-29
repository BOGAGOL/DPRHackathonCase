import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from verify import after_comparison as comparison, leak_sim, protected_artifact


def test_compare_reports_and_archive_preserves_history(tmp_path):
    scopes=('all','source_734','synthetic')
    before={'status':'PASSED','populations':{s:{'ESCE':{'ratio':1},'DIE':{'ratio':1}} for s in scopes},
            'ELS':{'bidx_count':0,'plaintext_equality_column_count':29}}
    residual={'status':'PASSED','populations':{s:{'combinations':[{'k_min':1}]} for s in scopes}}
    folder=tmp_path/'evidence/leakage'; folder.mkdir(parents=True)
    (folder/'baseline_dump.json').write_text(json.dumps(before))
    (folder/'residual_before.json').write_text(json.dumps(residual))
    small=folder/'baseline_100k'; small.mkdir()
    (small/'baseline_dump.json').write_text(json.dumps(before))
    (small/'residual_before.json').write_text(json.dumps(residual))
    for scale in ('100k','1m'):
        target=folder/('protected_'+scale);target.mkdir()
        (target/'residual_after.json').write_text(json.dumps(residual))
        for scenario in comparison.SCENARIOS:
            after={'status':'PASSED','dataset':'protected_'+scale,'scenario':scenario,
                'populations':{s:{'ESCE':{'ratio':0,'numerator':0,'denominator':1},'DIE':{'ratio':0,'numerator':0,'denominator':1}} for s in scopes},
                'ELS':{'bidx_count':3,'plaintext_equality_column_count':5},'DBR':{}}
            (target/(scenario+'.json')).write_text(json.dumps(after))
    destination=folder/'before_after.csv';destination.write_text('original before evidence')
    report=comparison.run(tmp_path)
    assert report['comparison_rows']==88 and len(report['scenarios'])==8
    assert (folder/'history/before_after_before_protected_20261028.csv').read_text()=='original before evidence'
    incomplete=folder/'protected_100k/protected_dump_no_key.json'
    value=json.loads(incomplete.read_text());value['status']='FAILED';incomplete.write_text(json.dumps(value))
    with pytest.raises(ValueError):comparison.run(tmp_path)


def test_leak_sim_dispatches_protected_to_real_adapter(monkeypatch,tmp_path):
    operation=MagicMock(return_value={'status':'PASSED'})
    monkeypatch.setattr(protected_artifact,'run',operation)
    assert leak_sim.run(tmp_path/'dump',tmp_path/'known',database='protected_100k',scenario='protected_dump_no_key')['status']=='PASSED'
    operation.assert_called_once_with(tmp_path/'dump',tmp_path/'known','protected_100k','protected_dump_no_key')
