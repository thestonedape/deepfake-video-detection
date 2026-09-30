import hashlib
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('checkpoint', Path(__file__).parents[1] / 'scripts/verify_checkpoint.py')
checkpoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoint)


def test_corrupt_checkpoint_is_rejected_without_download(tmp_path, monkeypatch):
    path = tmp_path / 'best_model.pt'
    path.write_bytes(b'corrupt')
    monkeypatch.setattr(checkpoint.urllib.request, 'urlretrieve', lambda *_: pytest.fail('Unexpected download'))
    with pytest.raises(RuntimeError, match='checksum'):
        checkpoint.verify(path)
    assert path.read_bytes() == b'corrupt'


def test_lfs_download_must_match_pinned_digest(tmp_path, monkeypatch):
    path = tmp_path / 'best_model.pt'
    pointer = b'version https://git-lfs.github.com/spec/v1\n'
    path.write_bytes(pointer)
    payload = b'verified test checkpoint'
    monkeypatch.setattr(checkpoint, 'SIZE', len(payload))
    monkeypatch.setattr(checkpoint, 'SHA256', hashlib.sha256(payload).hexdigest())
    def download(url, target):
        assert url == checkpoint.URL
        target.write_bytes(b'wrong artifact')
    monkeypatch.setattr(checkpoint.urllib.request, 'urlretrieve', download)
    with pytest.raises(RuntimeError):
        checkpoint.verify(path)
    assert path.read_bytes() == pointer
    assert not path.with_suffix('.download').exists()
    monkeypatch.setattr(checkpoint.urllib.request, 'urlretrieve', lambda url, target: target.write_bytes(payload))
    checkpoint.verify(path)
    assert path.read_bytes() == payload
