import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from infra.security import REPO
from .test_operator import material, read_env


def test_compose_cli_renders_without_exporting_passwords(material):
    docker=shutil.which("docker")
    if not docker: pytest.skip("Docker Compose CLI unavailable")
    env={**os.environ,**read_env(material/"compose.env")}
    result=subprocess.run([docker,"compose","-p","dpr-vm-render-test","-f",str(REPO/"infra/vm/compose.yaml"),"config","--format","json"],env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0, "Compose configuration failed; diagnostics withheld"
    config=json.loads(result.stdout)
    assert config["services"]["openbao"]["user"]=="1000:1000"
    for service,port in (("postgres","5433"),("openbao","8200")):
        published=config["services"][service]["ports"][0]
        assert published["host_ip"]=="127.0.0.1" and str(published["published"])==port
    from infra.vm.operator import credentials
    assert not any(value in result.stdout for value in credentials(material).values())


def test_bash_runbook_syntax_and_private_env_quoting(material,tmp_path):
    bash=Path("C:/Program Files/Git/bin/bash.exe") if os.name=="nt" else Path(shutil.which("bash") or "/missing/bash")
    if not bash.is_file(): pytest.skip("Native Bash unavailable")
    instructions=(REPO/"docs/OPERATIONS.md").read_text(encoding="utf-8")
    code="\n".join(re.findall(r"```bash\n(.*?)\n```",instructions,re.S))
    script=tmp_path/"runbook.bash";script.write_text(code,encoding="utf-8")
    parsed=subprocess.run([str(bash),"-n",script.as_posix()],capture_output=True,text=True,timeout=15)
    assert parsed.returncode==0, "Runbook Bash syntax failed"
    from infra.vm.operator import save_environment
    value="invented ' quote; $(should_not_execute)\nsecond line"
    private=material/"quote-check.env";save_environment(private,{"CHECK_VALUE":value})
    result=subprocess.run([str(bash),"--noprofile","--norc","-c",'. "$1"; test "$CHECK_VALUE" = "$2"',"_",private.as_posix(),value],capture_output=True,text=True,timeout=15)
    assert result.returncode==0 and not result.stdout and not result.stderr
