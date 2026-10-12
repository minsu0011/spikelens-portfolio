"""Verify the running project Docker image using isolated PostgreSQL/Redis test state.

Windows: backend/.venv/Scripts/python.exe scripts/test_backend_linux.py
Linux: python3 scripts/test_backend_linux.py

No credentials are passed in argv or printed. Production services remain running.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
import datetime,hashlib,importlib.metadata,json,os,pathlib,platform,subprocess,sys,time,xml.etree.ElementTree as ET
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
url=make_url(os.environ['DATABASE_URL'])
if url.host != 'postgres':
    raise SystemExit('Refusing tests outside this Compose PostgreSQL service')
secrets=[os.environ['DATABASE_URL'],url.password or '']
admin=create_engine(url.set(database='postgres'),connect_args={'connect_timeout':5})
try:
    with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        if not connection.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'),{'name':'spikelens_test'}):
            connection.execute(text('CREATE DATABASE spikelens_test'))
except Exception as exc:
    raise SystemExit('Local test database preparation failed: '+type(exc).__name__) from None
finally:
    admin.dispose()
os.environ['TEST_DATABASE_URL']=url.set(database='spikelens_test').render_as_string(hide_password=False)
os.environ['TEST_REDIS_URL']=os.environ['REDIS_URL'].rsplit('/',1)[0]+'/2'
os.environ['UPLOAD_DIR']='/tmp/spikelens-final-tests/uploads'
os.environ['JOB_LEASE_SECONDS']='10'
os.environ['APP_ENV']='test'
output=pathlib.Path('/app/test-output');output.mkdir(exist_ok=True)
def redact(value):
    for secret in secrets:
        if secret:value=value.replace(secret,'<REDACTED>')
    return value
start=time.monotonic()
lint=subprocess.run(['ruff','check','app','tests','alembic'],capture_output=True,text=True)
print(redact(lint.stdout+lint.stderr),flush=True)
result=subprocess.run([sys.executable,'-m','pytest','-q','--tb=short','--junitxml=/app/test-output/BACKEND_LINUX_TESTS.junit.xml'],capture_output=True,text=True)
print(redact(result.stdout+result.stderr),flush=True)
xml_path=output/'BACKEND_LINUX_TESTS.junit.xml'
if not xml_path.exists():
    raise SystemExit(result.returncode or 1)
xml_path.write_text(redact(xml_path.read_text()),encoding='utf-8')
root=ET.parse(xml_path).getroot();suites=list(root.iter('testsuite'))
counts={name:sum(int(s.attrib.get(name,0)) for s in suites) for name in ('tests','failures','errors','skipped')}
versions={name:importlib.metadata.version(name) for name in ['fastapi','pydantic','SQLAlchemy','psycopg','celery','redis','alembic','argon2-cffi','pytest','ruff','starlette','httpx']}
source=[{'path':str(p),'SHA256':hashlib.sha256(p.read_bytes()).hexdigest()} for directory in ['app','tests','alembic'] for p in pathlib.Path(directory).rglob('*.py')]
summary={'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'platform':platform.platform(),'python':sys.version,'uid':os.getuid(),'versions':versions,'test_environment':{'database':'spikelens_test','redis_database':2,'upload_dir':os.environ['UPLOAD_DIR'],'worker':'fixture-owned real Celery subprocess, pool solo','production_queue_and_upload_volume':'NOT_TOUCHED','lease_seconds':10},'test_counts':counts,'pytest_exit_code':result.returncode,'ruff_exit_code':lint.returncode,'elapsed_seconds':round(time.monotonic()-start,3),'source_sha256':source,'junit_sha256':hashlib.sha256(xml_path.read_bytes()).hexdigest()}
latency=output/'PUBLISHER_REFUSAL_LATENCY.json'
if latency.exists():summary['actual_publisher_refusal_latency']=json.loads(latency.read_text())
(output/'BACKEND_LINUX_VERIFICATION.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='source_sha256'},indent=2),flush=True)
sys.exit(result.returncode or lint.returncode)
"""


def compose_command(*args):
    return ["docker", "compose", *args]


def main():
    # Execute the current public image; report counts from this run only.
    result = subprocess.run(
        compose_command("exec", "-T", "backend", "python", "-"), input=HARNESS, text=True, cwd=ROOT
    )
    if result.returncode:
        # Preserve the last verified evidence; do not copy stale files as a new result.
        return result.returncode
    output = ROOT / "docs" / "evidence"
    output.mkdir(parents=True, exist_ok=True)
    copied = True
    for name, destination in [
        ("BACKEND_LINUX_TESTS.junit.xml", "BACKEND_LINUX_TESTS.junit.xml"),
        ("BACKEND_LINUX_VERIFICATION.json", "BACKEND_LINUX_VERIFICATION.json"),
        ("PUBLISHER_REFUSAL_LATENCY.json", "PUBLISHER_REFUSAL_LINUX.json"),
    ]:
        copied &= (
            subprocess.run(
                compose_command(
                    "cp", f"backend:/app/test-output/{name}", f"docs/evidence/{destination}"
                ),
                cwd=ROOT,
            ).returncode
            == 0
        )
    if copied:
        summary = json.loads(
            (output / "BACKEND_LINUX_VERIFICATION.json").read_text(encoding="utf-8")
        )
        print("Curated evidence: docs/evidence/BACKEND_LINUX_VERIFICATION.json")
        print("Tests:", summary["test_counts"])
    return result.returncode or (0 if copied else 1)


if __name__ == "__main__":
    raise SystemExit(main())
