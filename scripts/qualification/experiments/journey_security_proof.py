"""Qualify offline CLI/SDK privacy and tagged history with an installed candidate."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from scripts.qualification.interfaces.python_network_guard import guarded_engine

ROOT = Path(__file__).resolve().parents[3]

# Executed by the installed interpreter from a copied file outside the checkout.
PROBE = r'''
import hashlib, json, os, subprocess, sys
from pathlib import Path
import apizr
from apizr import telemetry, tracking
from apizr.experiments.comparison import compare_stored_runs, diff_bytes
from apizr.experiments.comparison_reporting import diff_text
from apizr.experiments.history import history_bytes, show_run
from apizr.experiments.serialization import read_plan, read_run
from apizr.experiments.store import DEFAULT_STORE
root = Path.cwd()
assert Path(apizr.__file__).resolve().is_relative_to(Path(sys.prefix))
env = {k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'}}
env.update(APIZR_TELEMETRY='0', APIZR_TELEMETRY_ALLOWED='0', APIZR_TELEMETRY_CONFIG=str(root/'consent.json'))
def cli(*args, code=0):
    result = subprocess.run([sys.executable,'-I','-B','-m','apizr.cli',*map(str,args)], cwd=root, env=env, capture_output=True, check=False, timeout=30)
    assert result.returncode == code, (args,result.stderr)
    return result
fixture = root/'historical'
store = root/'history'
for kind in ('plans','runs'): (store/kind).mkdir(parents=True)
retained = []
for name in ('a.record.json','b.record.json'):
    raw = (fixture/name).read_bytes()
    record = json.loads(raw)
    for kind,key in (('plans','plan'),('runs','run')):
        value = (json.dumps(record[key],sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
        (store/kind/(record[key+'_digest']+'.json')).write_bytes(value)
    admitted = show_run(store,record['run_digest'])
    assert history_bytes(admitted) == raw
    assert read_plan((store/'plans'/(record['plan_digest']+'.json')).read_bytes()) == admitted.plan
    assert read_run((store/'runs'/(record['run_digest']+'.json')).read_bytes()) == admitted.run
    assert cli('experiment','show',record['run_digest'],'--store',store,'--format','json').stdout == raw
    retained.append(record['run_digest'])
comparison = compare_stored_runs(store,*retained)
assert diff_bytes(comparison) == (fixture/'diff.json').read_bytes()
assert diff_text(comparison).encode() == (fixture/'diff.txt').read_bytes()
assert cli('experiment','diff',*retained,'--store',store,'--format','json').stdout == (fixture/'diff.json').read_bytes()
before = {str(p.relative_to(store)):p.read_bytes() for p in store.rglob('*.json')}
cli('providers','list','--format','json')
(root/'disabled.json').write_text('{"schema_version":"apizr.provider-selection/v1","providers":[]}')
(root/'model.py').write_text('value=7\n')
inspection = json.loads(cli('experiment','inspect','model.py','--providers','disabled.json','--format','json').stdout)
assert not inspection['providers']['active']
assert cli('experiment','show',retained[0],'--store',store,'--format','json').stdout == (fixture/'a.record.json').read_bytes()
assert before == {str(p.relative_to(store)):p.read_bytes() for p in store.rglob('*.json')}
cli('experiment','run','model.py','--format','json')
cli('experiment','list','--format','json')
preview = json.loads(cli('telemetry','preview').stdout)
assert not preview['collection_enabled'] and not preview['transmission_available']
assert json.loads(preview['payload'])['events'] == []
untrusted = root/'untrusted'
untrusted.mkdir()
(untrusted/'apizr.toml').write_text('schema_version="apizr.project/v1"\n')
selected_source = untrusted/'private-untrusted-source.py'
selected_source.write_text('raise AssertionError("Untrusted source executed")\n')
(root/'deny.json').write_text('{"schema":"apizr.operator-policy/v1","grants":[]}')
source_guard = """import sys,runpy
def audit(event,args):
    if event=='open' and str(args[0]).endswith('private-untrusted-source.py'):
        raise AssertionError('untrusted source read before authorization')
sys.addaudithook(audit)
sys.argv=['apizr',*sys.argv[1:]]
runpy.run_module('apizr.cli',run_name='__main__')
"""
request = json.dumps({'request_id':'untrusted-proof','operation':'inspect','arguments':{'source':selected_source.name}})
refusal = subprocess.run([sys.executable,'-I','-B','-c',source_guard,'editor','--project',str(untrusted/'apizr.toml'),'--operator-policy',str(root/'deny.json')], input=request.encode(), env=env, capture_output=True, timeout=30)
assert refusal.returncode == 2 and not refusal.stderr
refused = json.loads(refusal.stdout)
assert not refused['ok'] and refused['diagnostics'][0]['code'] == 'operator_operation_denied', refused
(root/'sensitive-artifact.bin').write_bytes(b'PRIVATE_FILE_CONTENT')
with telemetry.capture(environ={'APIZR_TELEMETRY':'1','APIZR_TELEMETRY_CONFIG':str(root/'private-consent.json')}) as usage:
    with tracking.session(root=root) as capture:
        tracking.log_parameter('PRIVATE_PARAMETER','PRIVATE_VALUE')
        tracking.log_metric('PRIVATE_METRIC',0.987654321)
        tracking.log_input('PRIVATE_INPUT', uri='https://example.invalid/PRIVATE_REMOTE')
        tracking.log_artifact('PRIVATE_ARTIFACT','sensitive-artifact.bin')
    failure = RuntimeError('PRIVATE_TRACEBACK')
    try:
        with tracking.session(root=root): raise failure
    except RuntimeError as observed: assert observed is failure
    report = usage.preview()
    payload = json.loads(report['payload'])
    assert sorted(payload['events'],key=lambda e:e['outcome']) == [
        {'operation':'capture_session','outcome':'failed','count':1},
        {'operation':'capture_session','outcome':'success','count':1}]
    assert not report['transmission_available']
    for secret in ('PRIVATE',str(root),'sensitive-artifact.bin','0.987654321','run_digest','traceback'):
        assert secret not in report['payload']
    assert 'telemetry' not in capture.record.model_dump_json()
    (root/'preview.json').write_text(json.dumps(report,sort_keys=True)+'\n')
corrupt = store/'runs'/(retained[0]+'.json')
raw = corrupt.read_bytes()
try:
    corrupt.write_bytes(raw.replace(b'"status":"success"',b'"status":"failed"'))
    assert corrupt.read_bytes() != raw
    result = cli('experiment','show',retained[0],'--store',store,'--format','json',code=2)
    assert b'store_corrupt' in result.stderr and b'Traceback' not in result.stderr
finally: corrupt.write_bytes(raw)
proof = {'result':'pass','installed_package':str(Path(apizr.__file__).resolve()),
         'historical_tag':'v0.4.5','historical_records':retained,
         'canonical_show_diff':'byte-identical','provider_disabled_history':'passed',
         'tampered_run':'store_corrupt','telemetry_sensitive_values':'absent',
         'untrusted_source_before_authorization':'not read or executed',
         'telemetry_scientific_evidence_separation':'passed','production_transmission':False,
         'offline_surfaces':['CLI inspect/run/history/providers/preview','SDK success/failure with explicit observations']}
(root/'proof.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
'''


def prove(python: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    fixtures = ROOT / "tests/fixtures/experiments/compatibility-0.4.5"
    provenance = json.loads((fixtures / "provenance.json").read_text())
    for name, record in provenance["files"].items():
        assert (
            hashlib.sha256((fixtures / name).read_bytes()).hexdigest()
            == record["sha256"]
        )
    shutil.copytree(fixtures, output / "historical")
    probe = output / "probe.py"
    probe.write_text(PROBE)
    with guarded_engine(python, output / "network.log") as network:
        result = subprocess.run(
            [str(python), "-I", "-B", str(probe)],
            cwd=output,
            capture_output=True,
            text=True,
            timeout=120,
        )
        (output / "probe.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
    assert network["apizr_processes"] >= 10
    proof = json.loads((output / "proof.json").read_text())
    proof.update(network=network, historical_source=provenance)
    assert not Path(proof["installed_package"]).is_relative_to(ROOT)
    (output / "proof.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True) + "\n"
    )
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prove(args.python.absolute(), args.output.resolve())))


if __name__ == "__main__":
    main()
