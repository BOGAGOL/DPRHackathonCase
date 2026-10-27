from datetime import date, datetime
import hashlib
import hmac
import os
from uuid import UUID

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dprcrypto import DecryptionError, OpenBaoError
from infra.protected.apply import load_profile
from infra.security import REPO
from migration.model import (MigrationError,age_band,blind_indexes,canonical_value,compare_batch,
                             protect_batch,source_bytes,target_columns)
from migration.runner import check_pair


@pytest.fixture
def profile():return load_profile(REPO/"policy/protection_profile.yaml")


def synthetic_row(index,profile):
    row={column:"Synthetic "+str(index) for column in profile["columns"]}
    row.update(id=index,tanggal_lahir=date(1986,10,2),tanggal_pernikahan=None,
               jenis_kelamin="L",jumlah_anak=0,jumlah_tanggungan=2,jumlah_jiwa=3,
               no_ktp=f"09{index:012d}",email=f"case{index}@example.invalid",pengguna=f"User {index}")
    return row


class SyntheticTransit:
    """Invented in-memory KEK; no substitute for the real integration test."""
    def __init__(self):
        self.keys={name:os.urandom(32) for name in ("pii-kek","finance-kek")}
        self.search=os.urandom(32);self.wrapped={};self.calls=[]
    def wrap_batch(self,kek,deks):
        import base64
        result=[]
        for dek in deks:
            nonce=os.urandom(12)
            wrapped="vault:v1:"+base64.b64encode(nonce+AESGCM(self.keys[kek]).encrypt(nonce,dek,None)).decode()
            self.wrapped[wrapped]=dek;result.append(wrapped)
        self.calls.append((kek,len(deks)));return result
    def unwrap_batch(self,kek,wrapped):return [self.wrapped[value] for value in wrapped]
    def hmac_batch(self,messages,**kwargs):return [hmac.new(self.search,message,hashlib.sha256).digest() for message in messages]


def test_canonical_values_and_source_fingerprint(profile):
    assert str(MigrationError(os.urandom(24).hex()))=="migration_failed"
    assert canonical_value(None) is None and canonical_value("00012")=="00012"
    assert canonical_value(0)=="0" and canonical_value(date(2000,2,29))=="2000-02-29"
    for value in (True,1.2,datetime.now(),b"synthetic"):
        with pytest.raises(MigrationError):canonical_value(value)
    row=synthetic_row(1,profile)
    assert source_bytes(row,list(profile["columns"])).endswith(b"\n")
    assert len(target_columns(profile))==38


def test_age_bands_boundary_leap_day_and_null(profile):
    assert age_band(None,profile) is None
    assert age_band(date(1986,10,1),profile)=="40-49"
    assert age_band(date(1986,10,2),profile)=="30-39"
    assert age_band("2000-02-29",profile)=="20-29"
    for value in ("bad-date","2027-01-01"):
        with pytest.raises(MigrationError):age_band(value,profile)


def test_local_aead_domains_nulls_nonces_and_full_compare(profile):
    rows=[synthetic_row(i,profile) for i in range(1,4)]
    rows[1]["email"]=None
    transit=SyntheticTransit()
    protected=protect_batch(rows,profile,transit)
    assert len(protected)==3 and all(UUID(row["anggota_id"]).version==4 for row in protected)
    assert len({row["dek_pii_wrapped"] for row in protected})==3
    assert all(row["dek_pii_wrapped"]!=row["dek_fin_wrapped"] for row in protected)
    assert protected[1]["email_ct"] is None and protected[1]["email_bidx"] is None
    nulls=compare_batch(rows,protected,profile,transit)
    assert nulls["tanggal_pernikahan"]==3 and nulls["email"]==1
    repeated=protect_batch(rows,profile,transit)
    assert repeated[0]["nama_ct"]!=protected[0]["nama_ct"]
    assert repeated[0]["email_bidx"]==protected[0]["email_bidx"]


@pytest.mark.parametrize("mutation",["bit","record_swap","column_swap","null","ref","band","bidx","identity","version","missing"])
def test_tamper_and_swaps_never_pass_validation(profile,mutation):
    rows=[synthetic_row(i,profile) for i in (1,2)]
    transit=SyntheticTransit();protected=protect_batch(rows,profile,transit)
    if mutation=="bit":
        raw=bytearray(protected[0]["nama_ct"]);raw[-1]^=1;protected[0]["nama_ct"]=bytes(raw)
    elif mutation=="record_swap":protected[0]["nama_ct"]=protected[1]["nama_ct"]
    elif mutation=="column_swap":protected[0]["nama_ct"]=protected[0]["alamat_jakarta_ct"]
    elif mutation=="null":protected[0]["nama_ct"]=None
    elif mutation=="ref":protected[0]["nama_bank"]="Different synthetic bank"
    elif mutation=="band":protected[0]["age_band"]="90-99"
    elif mutation=="bidx":protected[0]["email_bidx"]=os.urandom(32)
    elif mutation=="identity":protected[0]["legacy_row_id"]=999
    elif mutation=="version":protected[0]["protection_version"]=2
    else:protected.pop()
    with pytest.raises((MigrationError,DecryptionError)):
        compare_batch(rows,protected,profile,transit)


def test_bounds_partial_batch_and_pair_guard(profile):
    row=synthetic_row(1,profile);transit=SyntheticTransit()
    with pytest.raises(MigrationError):protect_batch([row]*101,profile,transit)
    class Partial(SyntheticTransit):
        def wrap_batch(self,*args):return []
        def hmac_batch(self,*args,**kwargs):return []
    with pytest.raises(MigrationError):protect_batch([row],profile,Partial())
    with pytest.raises(MigrationError):blind_indexes(Partial(),"email",["synthetic@example.invalid"],1)
    assert blind_indexes(transit,"email",[None,None],1)==[None,None]
    for pair in (("postgres","postgres"),("postgres","protected_100k"),("baseline_100k","protected_734")):
        with pytest.raises(MigrationError):check_pair(*pair)
    check_pair("postgres","protected_734")
