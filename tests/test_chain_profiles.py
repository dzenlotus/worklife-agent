import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READ_PROFILE = """
import json, os
from worklife import chain_profile as profile, qualification
os.environ['WORKLIFE_CHAIN_PROFILE'] = 'changed-after-import'
print(json.dumps({
    'profile': profile.PROFILE, 'network': profile.NETWORK,
    'block_bits': profile.BLOCK_BITS, 'qualification_bits': profile.QUALIFICATION_BITS,
    'confirmations': profile.CONFIRMATIONS,
    'challenge_network': qualification.challenge('0' * 64, 'a' * 64, '2026-10-01T00:00:00Z')['network'],
    'qualification_network': qualification.NETWORK, 'work_domain': qualification.WORK_DOMAIN.decode(),
    'sign_domain': qualification.SIGN_DOMAIN.decode(), 'qualification_work_bits': qualification.QUALIFICATION_BITS,
}))
"""


def read_profile(name=None, code=READ_PROFILE):
    env = os.environ.copy()
    env.pop("WORKLIFE_CHAIN_PROFILE", None)
    if name is not None:
        env["WORKLIFE_CHAIN_PROFILE"] = name
    env["WORKLIFE_BLOCK_BITS"] = "1"
    env["WORKLIFE_QUALIFICATION_BITS"] = "1"
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, text=True, capture_output=True)


@pytest.mark.parametrize("name", [None, "development"])
def test_development_profile_preserves_existing_rules_and_domains(name):
    result = read_profile(name)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "profile": "development",
        "network": "worklife-chain-v1",
        "block_bits": 12,
        "qualification_bits": 10,
        "confirmations": 3,
        "challenge_network": "worklife-chain-v1",
        "qualification_network": "worklife-chain-v1",
        "qualification_work_bits": 10,
        "work_domain": "worklife-chain-v1/qualification/v1/work\0",
        "sign_domain": "worklife-chain-v1/qualification/v1/signature\0",
    }


def test_public_profile_is_fixed_and_selected_once_per_process():
    result = read_profile("public-testnet-v1")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "profile": "public-testnet-v1",
        "network": "worklife-public-testnet-v1",
        "block_bits": 25,
        "qualification_bits": 18,
        "confirmations": 6,
        "challenge_network": "worklife-public-testnet-v1",
        "qualification_network": "worklife-public-testnet-v1",
        "qualification_work_bits": 18,
        "work_domain": "worklife-public-testnet-v1/qualification/v1/work\0",
        "sign_domain": "worklife-public-testnet-v1/qualification/v1/signature\0",
    }


def test_profiles_have_separate_genesis_and_publish_their_actual_rules():
    code = """
import json, tempfile
from worklife.blockchain import Blockchain
from worklife.ledger import Ledger
from worklife.storage import Store
with tempfile.TemporaryDirectory() as home:
    store = Store(home)
    print(json.dumps(Blockchain(store, Ledger(store)).status()))
"""
    statuses = []
    for name, network, bits, qualification_bits, confirmations in (
        ("development", "worklife-chain-v1", 12, 10, 3),
        ("public-testnet-v1", "worklife-public-testnet-v1", 25, 18, 6),
    ):
        result = read_profile(name, code)
        assert result.returncode == 0, result.stderr
        status = json.loads(result.stdout)
        assert status["profile"] == name
        assert status["network"] == status["rules"]["network"] == network
        assert status["block_bits"] == status["rules"]["block_bits"] == bits
        assert status["confirmations"] == status["rules"]["confirmations"] == confirmations
        assert status["rules"]["qualification_bits"] == qualification_bits
        statuses.append(status)
    assert statuses[0]["genesis"] == "3222f0fd06f1a45f14dda23f477bde3b4adfca410958eb9884dcf9945a19bf57"
    assert statuses[1]["genesis"] != statuses[0]["genesis"]


@pytest.mark.parametrize("name", ["", "production", "public-testnet-v1 ", "Development"])
def test_unknown_profile_fails_closed(name):
    result = read_profile(name)
    assert result.returncode != 0
    assert "ValueError: Unknown WORKLIFE_CHAIN_PROFILE" in result.stderr
